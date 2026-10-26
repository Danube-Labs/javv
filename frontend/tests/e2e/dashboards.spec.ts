/**
 * A dashboard from start to end (issue 440, S8c), on the seeded stack: a user who can edit
 * dashboards makes one, adds two panels, moves one with the mouse, shares it with the viewer
 * role and saves. The viewer opens it and cannot change it. The maker then removes it, so the
 * store is left as found. The seed has the admin and the viewer only, so the admin makes it.
 */
import type { Page } from '@playwright/test'

import { BASE, expect, login, loginViewer, test } from './helpers'

async function addPanel(page: Page, id: string, name: string) {
  await page.getByRole('button', { name: 'Add panel', exact: true }).first().click()
  const dialog = page.getByRole('dialog')
  await dialog.locator(`.cat-row[data-panel="${id}"]`).click()
  await dialog.getByRole('button', { name: 'Add panel', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('button', { name: `Move ${name}`, exact: true })).toBeVisible({ timeout: 20_000 })
}

test('a dashboard is made, moved, shared and removed; the viewer cannot change it', async ({ page, browser }) => {
  test.setTimeout(120_000)
  const name = `e2e dashboard ${Date.now()}`
  await login(page)
  await page.goto(`${BASE}/dashboards`)

  // make it, shared with the viewer role
  await page.locator('.head-actions').getByRole('button', { name: 'New dashboard' }).click()
  const details = page.getByRole('dialog', { name: 'New dashboard' })
  await details.locator('#dash-name').fill(name)
  await details.getByRole('button', { name: 'Some roles' }).click()
  await details.getByRole('group', { name: 'Roles that can see the dashboard' }).getByRole('button', { name: 'viewer' }).click()
  await details.getByRole('button', { name: 'Create' }).click()
  // the app keeps the selected cluster in the URL too
  await expect(page).toHaveURL(/\/dashboards\/[0-9a-f]{32}\?(.*&)?edit=1(&|$)/)
  const id = /\/dashboards\/([0-9a-f]{32})/.exec(page.url())![1]!

  try {
    await expect(page.locator('h1')).toHaveText(`Editing ${name}`)
    await addPanel(page, 'findings-summary', 'Findings summary')
    await addPanel(page, 'triage-progress', 'Triage progress')

    // move Triage progress over Findings summary, with the mouse on its Move tab
    const item = page.locator('.grid-stack-item[data-panel="triage-progress"]')
    const handle = item.locator('.dash-move')
    const target = page.locator('.grid-stack-item[data-panel="findings-summary"]')
    await handle.scrollIntoViewIfNeeded()
    const hb = (await handle.boundingBox())!
    const tb = (await target.boundingBox())!
    await page.mouse.move(hb.x + hb.width / 2, hb.y + hb.height / 2)
    await page.mouse.down()
    await page.mouse.move(hb.x + 40, hb.y - 20, { steps: 5 })
    await page.mouse.move(tb.x + 60, tb.y + 10, { steps: 15 })
    await page.mouse.up()
    await expect(item).toHaveAttribute('gs-y', '0')

    const saved = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes(id))
    await page.getByRole('button', { name: 'Save changes' }).click()
    expect((await saved).status()).toBe(200)

    // the server holds the move and the sharing
    const stored = await (await page.request.get(`${BASE}/api/v1/dashboards/${id}`)).json()
    expect(stored.sharing).toBe('roles')
    expect(stored.roles).toEqual(['viewer'])
    const triage = stored.panels.find((p: { panel: string }) => p.panel === 'triage-progress')
    expect(triage.y).toBe(0)

    // the viewer sees it, and cannot change it
    const viewerContext = await browser.newContext()
    try {
      const viewer = await viewerContext.newPage()
      await loginViewer(viewer)
      await viewer.goto(`${BASE}/dashboards/${id}`)
      await expect(viewer.locator('h1')).toHaveText(name, { timeout: 20_000 })
      await expect(viewer.getByRole('button', { name: 'Edit dashboard' })).toBeDisabled()
      await expect(viewer.locator('#no-edit-note')).toHaveText('Your role cannot change dashboards.')
    } finally {
      await viewerContext.close()
    }

    // remove it, after the confirmation
    await page.getByRole('button', { name: 'Remove', exact: true }).click()
    await page.getByRole('dialog').getByRole('button', { name: 'Remove dashboard' }).click()
    await expect(page).toHaveURL(/\/dashboards(\?|$)/)
    expect((await page.request.get(`${BASE}/api/v1/dashboards/${id}`)).status()).toBe(404)
  } finally {
    // a failed step above must not leave the dashboard in the shared store
    const left = await page.request.get(`${BASE}/api/v1/dashboards/${id}`)
    if (left.ok()) {
      const { revision } = await left.json()
      await page.request.delete(`${BASE}/api/v1/dashboards/${id}?revision=${revision}`)
    }
  }
})

test('a panel added next to a taller one is saved where edit mode shows it', async ({ page }) => {
  await login(page)
  const made = await page.request.post(`${BASE}/api/v1/dashboards`, {
    data: {
      name: `e2e packed panel ${Date.now()}`,
      description: '',
      scanner: 'all',
      sharing: 'private',
      roles: [],
      panels: [
        { panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short' },
        { panel: 'top-components', x: 1, y: 7, w: 1, h: 'short' },
      ],
    },
  })
  expect(made.status()).toBe(201)
  const { dashboard_id: id } = await made.json()
  try {
    await page.goto(`${BASE}/dashboards/${id}?edit=1`)
    await expect(page.getByRole('button', { name: 'Move Top components', exact: true })).toBeVisible({ timeout: 20_000 })
    // the left column under Findings summary is empty, so top mode packs the new half panel up into it
    await addPanel(page, 'triage-progress', 'Triage progress')
    const item = page.locator('.grid-stack-item[data-panel="triage-progress"]')
    await expect(item).toHaveAttribute('gs-y', '7')

    const saved = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes(id))
    await page.getByRole('button', { name: 'Save changes' }).click()
    expect((await saved).status()).toBe(200)
    const stored = await (await page.request.get(`${BASE}/api/v1/dashboards/${id}`)).json()
    const triage = stored.panels.find((p: { panel: string }) => p.panel === 'triage-progress')
    expect([triage.x, triage.y]).toEqual([0, 7])
  } finally {
    const left = await page.request.get(`${BASE}/api/v1/dashboards/${id}`)
    if (left.ok()) {
      const { revision } = await left.json()
      await page.request.delete(`${BASE}/api/v1/dashboards/${id}?revision=${revision}`)
    }
  }
})

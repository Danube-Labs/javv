/**
 * A dashboard from start to end (issue 440, S8c), on the seeded stack: a user who can edit
 * dashboards makes one, adds two panels, moves one with the mouse, shares it with the viewer
 * role and saves. The viewer opens it and cannot change it. The maker then removes it, so the
 * store is left as found. The seed has the admin and the viewer only, so the admin makes it.
 * Each panel is as tall as its content in both modes (issue 1045), which only a real browser
 * measures.
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

/** A dashboard made through the API, which `fn` uses and the finally block removes. */
async function withDashboard(page: Page, panels: unknown[], fn: (id: string) => Promise<void>) {
  const made = await page.request.post(`${BASE}/api/v1/dashboards`, {
    data: { name: `e2e layout ${Date.now()}`, description: '', scanner: 'all', sharing: 'private', roles: [], panels },
  })
  expect(made.status()).toBe(201)
  const { dashboard_id: id } = await made.json()
  try {
    await fn(id)
  } finally {
    const left = await page.request.get(`${BASE}/api/v1/dashboards/${id}`)
    if (left.ok()) {
      const { revision } = await left.json()
      await page.request.delete(`${BASE}/api/v1/dashboards/${id}?revision=${revision}`)
    }
  }
}

/** For each panel: how much its content overflows it, and the gap above it in its column. */
function readLayout(page: Page) {
  return page.evaluate(() => {
    const gap = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--grid-gap'))
    const box = (el: Element) => el.getBoundingClientRect()
    const cells = [...document.querySelectorAll<HTMLElement>('.dash-cell')].map((c) => ({
      panel: c.dataset.panel,
      overflow: c.scrollHeight - c.clientHeight,
      cut: Math.max(0, ...[...c.children].map((k) => box(k).bottom - box(c).bottom)),
      clips: getComputedStyle(c).overflowY !== 'visible',
    }))
    const gaps: number[] = []
    for (const stack of document.querySelectorAll('.dash-stack')) {
      const kids = [...stack.children]
      for (let i = 1; i < kids.length; i++) gaps.push(box(kids[i]!).top - box(kids[i - 1]!).bottom)
    }
    const blocks = [...document.querySelectorAll('.dash-block')]
    for (let i = 1; i < blocks.length; i++) gaps.push(box(blocks[i]!).top - box(blocks[i - 1]!).bottom)
    return { gap, cells, gaps }
  })
}

const LAYOUT = [
  { panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short' },
  { panel: 'riskiest-images', x: 0, y: 7, w: 1, h: 'short' },
  { panel: 'top-components', x: 1, y: 7, w: 1, h: 'short' },
  { panel: 'triage-progress', x: 0, y: 20, w: 1, h: 'short' },
  { panel: 'scan-ingest', x: 0, y: 30, w: 2, h: 'short' },
]

test('the read page: each panel is as tall as its content, and the gaps are the grid gap', async ({ page }) => {
  await login(page)
  await withDashboard(page, LAYOUT, async (id) => {
    await page.goto(`${BASE}/dashboards/${id}`)
    await expect(page.locator('.dash-cell')).toHaveCount(LAYOUT.length, { timeout: 20_000 })
    await expect(page.locator('.dash-grid .skel')).toHaveCount(0, { timeout: 20_000 })
    // block by block, the left column first
    expect(await page.locator('.dash-cell').evaluateAll((cs) => cs.map((c) => (c as HTMLElement).dataset.panel))).toEqual([
      'findings-summary',
      'riskiest-images',
      'triage-progress',
      'top-components',
      'scan-ingest',
    ])
    const { gap, cells, gaps } = await readLayout(page)
    for (const c of cells) {
      expect(c, `${c.panel} scrolls, is cut or clips its shadow`).toMatchObject({ overflow: 0, cut: 0, clips: false })
    }
    // one gap in the left column, and one between each two blocks
    expect(gaps).toHaveLength(3)
    for (const g of gaps) expect(Math.abs(g - gap)).toBeLessThanOrEqual(1)
  })
})

test('edit mode: each panel takes the rows of its content, and opening it is not a change', async ({ page }) => {
  await login(page)
  await withDashboard(page, LAYOUT, async (id) => {
    await page.goto(`${BASE}/dashboards/${id}?edit=1`)
    await expect(page.locator('.grid-stack-item')).toHaveCount(LAYOUT.length, { timeout: 20_000 })
    await expect(page.locator('.grid-stack .skel')).toHaveCount(0, { timeout: 20_000 })
    // the content of each panel ends inside its rows, and the next panel starts under it
    await expect
      .poll(() =>
        page.locator('.grid-stack-item').evaluateAll((items) =>
          items.map((item) => {
            const fit = item.querySelector('.dash-fit')!.getBoundingClientRect()
            const body = item.querySelector('.grid-stack-item-content')!.getBoundingClientRect()
            return Math.round(Math.max(0, fit.bottom - body.bottom))
          }),
        ),
      )
      .toEqual(LAYOUT.map(() => 0))
    await expect(page.locator('.save-msg')).toHaveText('All changes saved')
    await expect(page.getByRole('button', { name: 'Exit edit' })).toBeEnabled()
  })
})

test('the Add panel preview is as tall as its content, as on the dashboard', async ({ page }) => {
  await login(page)
  await withDashboard(page, LAYOUT, async (id) => {
    await page.goto(`${BASE}/dashboards/${id}?edit=1`)
    await expect(page.getByRole('button', { name: 'Move Findings summary', exact: true })).toBeVisible({ timeout: 20_000 })
    await page.getByRole('button', { name: 'Add panel', exact: true }).first().click()
    const dialog = page.getByRole('dialog')
    for (const [panel, height] of [['findings-summary', null], ['riskiest-images', 'Tall']] as const) {
      await dialog.locator(`.cat-row[data-panel="${panel}"]`).click()
      if (height) await dialog.getByRole('button', { name: height, exact: true }).click()
      await expect(dialog.locator('.cat-prev .skel')).toHaveCount(0, { timeout: 20_000 })
      const fit = await dialog.locator('.cat-prev').evaluate((box) => ({
        overflow: box.scrollHeight - box.clientHeight,
        cut: Math.max(0, ...[...box.children].map((k) => k.getBoundingClientRect().bottom - box.getBoundingClientRect().bottom)),
      }))
      expect(fit, `${panel} scrolls or is cut in the preview`).toEqual({ overflow: 0, cut: 0 })
    }
  })
})

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
    // the left column under Findings summary is empty, so top mode packs the new half panel up into
    // it, right under the rows that the content of Findings summary takes
    await addPanel(page, 'triage-progress', 'Triage progress')
    const item = page.locator('.grid-stack-item[data-panel="triage-progress"]')
    const summary = page.locator('.grid-stack-item[data-panel="findings-summary"]')
    await expect.poll(async () => (await item.getAttribute('gs-y')) === (await summary.getAttribute('gs-h'))).toBe(true)
    const rows = Number(await summary.getAttribute('gs-h'))

    const saved = page.waitForResponse((r) => r.request().method() === 'PATCH' && r.url().includes(id))
    await page.getByRole('button', { name: 'Save changes' }).click()
    expect((await saved).status()).toBe(200)
    const stored = await (await page.request.get(`${BASE}/api/v1/dashboards/${id}`)).json()
    const triage = stored.panels.find((p: { panel: string }) => p.panel === 'triage-progress')
    expect([triage.x, triage.y]).toEqual([0, rows])
  } finally {
    const left = await page.request.get(`${BASE}/api/v1/dashboards/${id}`)
    if (left.ok()) {
      const { revision } = await left.json()
      await page.request.delete(`${BASE}/api/v1/dashboards/${id}?revision=${revision}`)
    }
  }
})

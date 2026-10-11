/**
 * A fresh install, before any cluster is listed (issue 817). The rigs seed clusters and mint
 * through the API, so this path was never walked: here the cluster list answers empty, and a new
 * user must be able to reach the mint dialog, mint for a cluster nobody has listed yet, and read
 * why the per-cluster settings are empty.
 */
import type { Page } from '@playwright/test'

import { BASE, expect, login, test } from './helpers'

async function noClusters(page: Page) {
  await page.route(
    (url) => url.pathname === '/api/v1/clusters',
    (route) => route.fulfill({ json: { clusters: [] } }),
  )
}

test.beforeEach(async ({ page }) => {
  await noClusters(page)
  await login(page)
})

test('the cold-start button is one keyboard stop and opens Access & tokens', async ({ page }) => {
  await page.goto(`${BASE}/overview`)
  const cta = page.getByRole('button', { name: 'Create a scanner token' })
  await expect(cta).toBeVisible()
  // walk the tab order up to the button: the stop before it must not be inside the empty state
  const stops: string[] = []
  for (let i = 0; i < 60 && !(await cta.evaluate((b) => b === document.activeElement)); i++) {
    await page.keyboard.press('Tab')
    stops.push(await page.evaluate(() => (document.activeElement?.closest('.empty-state') ? 'empty-state' : 'outside')))
  }
  await expect(cta).toBeFocused()
  expect(stops.filter((s) => s === 'empty-state')).toEqual(['empty-state']) // the button itself, once
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/settings\/tokens/)
})

test('the mint dialog opens on a new cluster with its ID field', async ({ page }) => {
  await page.goto(`${BASE}/settings/tokens`)
  await page.getByRole('button', { name: 'Mint token' }).click()
  await expect(page.locator('select#mint-cluster')).toHaveValue('+new')
  await expect(page.locator('#mint-cluster-id')).toBeVisible()
  await page.locator('#mint-cluster-id').fill('My-Cluster')
  await expect(page.getByRole('alert')).toContainText('8 to 64 characters')
  await expect(page.locator('.modal-actions').getByRole('button', { name: 'Mint token' })).toBeDisabled()
})

for (const path of ['scan-scope', 'scanning', 'data-opensearch']) {
  test(`settings/${path} says why it is empty instead of loading forever`, async ({ page }) => {
    await page.goto(`${BASE}/settings/${path}`)
    await expect(page.getByText('Settings for a cluster appear once it has a scanner token.')).toBeVisible()
    await expect(page.locator('.skel')).toHaveCount(0)
  })
}

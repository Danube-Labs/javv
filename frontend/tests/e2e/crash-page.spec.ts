/**
 * A page that fails while it is drawn, or whose file fails to load, shows the error page inside
 * the frame (issue 675). jsdom proves the boundary's rule; only a real build proves the phase
 * codes a production bundle reports, and that the sidebar still works afterwards.
 */
import type { Page } from '@playwright/test'

import { ABOUT_FILE, BASE, expect, login, test } from './helpers'

async function openAboutFromSidebar(page: Page) {
  await page.goto(`${BASE}/overview`)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 20_000 })
  await page.locator('.sidebar a.side-item[href^="/about"]').click()
}

test.beforeEach(async ({ page }) => {
  await login(page)
})

test('a page that throws while it is set up is replaced by the error page', async ({ page }) => {
  await page.route(ABOUT_FILE, (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: "export default { setup() { throw new Error('forced crash') } }",
    }),
  )
  await openAboutFromSidebar(page)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('JAVV cannot show this page')
  await expect(page.locator('.sidebar')).toBeVisible()

  // the frame still works: the sidebar leaves the broken page
  await page.locator('.sidebar a.side-item[href^="/findings"]').click()
  await expect(page).toHaveURL(/\/findings/)
  await expect(page.getByRole('heading', { level: 1 })).not.toHaveText('JAVV cannot show this page')
})

test('a page whose file fails to load shows the error page, and "Try again" recovers', async ({ page }) => {
  await page.route(ABOUT_FILE, (route) => route.abort())
  await openAboutFromSidebar(page)
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('JAVV cannot show this page')

  await page.unroute(ABOUT_FILE)
  await page.getByRole('button', { name: 'Try again' }).click()
  await expect(page.getByRole('heading', { level: 1 })).not.toHaveText('JAVV cannot show this page')
})

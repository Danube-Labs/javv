/**
 * A backend that stops answering (issue 675): the banner names the backend, not OpenSearch, as
 * soon as a request fails; the login page says the server is down instead of rejecting the
 * password. The dead backend is simulated at the browser: every backend path answers 502, which
 * is what a proxy with nothing behind it sends.
 */
import type { Page } from '@playwright/test'

import { BASE, DATA_ROW, PASS, USER, expect, login, test } from './helpers'

// the backend's own paths only: a bare /api/ pattern would also catch the dev server's /src/api/ modules
const isBackend = (url: URL) => /^\/(api|auth|readyz)(\/|$)/.test(url.pathname)
const kill = (page: Page) =>
  page.route(isBackend, (route) =>
    route.fulfill({ status: 502, contentType: 'text/html', body: '<html>502 Bad Gateway</html>' }),
  )

test('signed in: the banner names the backend at the first failed request', async ({ page }) => {
  await login(page)
  await page.goto(`${BASE}/findings`)
  await expect(page.locator(DATA_ROW).first()).toBeVisible({ timeout: 20_000 })
  await kill(page)
  await page.locator('.sidebar a.side-item[href^="/images"]').click()
  const banner = page.locator('.sys-line.tone-down[role="alert"]')
  await expect(banner).toContainText('The backend does not answer', { timeout: 10_000 })
  await expect(banner).not.toContainText('OpenSearch')
  await expect(page.locator('.sidebar .sweep')).toContainText('Backend not answering')
})

test('opening the app: the login page says the server is down, and never blames the password', async ({ page }) => {
  await kill(page)
  await page.goto(`${BASE}/findings`)
  await expect(page).toHaveURL(/\/login/)
  const notice = page.getByRole('alert')
  await expect(notice).toContainText('The backend does not answer')
  await page.fill('#username', USER)
  await page.fill('#password', PASS)
  await page.click('button[type=submit]')
  await expect(notice).toContainText('The backend does not answer')
  await expect(page.getByText('Invalid username or password')).toHaveCount(0)
})

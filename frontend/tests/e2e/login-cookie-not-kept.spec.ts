/**
 * A sign-in whose cookie the browser did not keep (issue 869), in a real browser against the real
 * backend: the sign-in answer loses its Set-Cookie header, as a browser drops a Secure cookie on
 * plain http. The suite runs on localhost, a secure context, so the http case also reports the
 * page as not one. The form must say why and stay on sign-in, never report success.
 */
import type { Page } from '@playwright/test'

import { BASE, PASS, USER, expect, test } from './helpers'

async function signInWithoutTheCookie(page: Page): Promise<void> {
  await page.route('**/auth/login', async (route) => {
    // route.fetch() goes through the context's own cookie jar, so the cookie is already in it:
    // take it out before the page gets the answer, and the answer without its header
    const answer = await route.fetch()
    await page.context().clearCookies({ name: 'javv_session' })
    const headers = { ...answer.headers() }
    delete headers['set-cookie']
    await route.fulfill({ response: answer, headers })
  })
  await page.goto(`${BASE}/login`)
  await page.fill('#username', USER)
  await page.fill('#password', PASS)
  await page.click('button[type=submit]')
}

test('on plain http, the form names https and the cookie setting', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, 'isSecureContext', { value: false }))
  await signInWithoutTheCookie(page)
  await expect(page.getByRole('alert')).toHaveText(
    'This browser refused the session cookie, because the page uses http. Use https, or ask ' +
      'the admin to set JAVV_SESSION_COOKIE_SECURE=false.',
  )
  expect(page.url()).toContain('/login')
})

test('on https or localhost, the form says the session was not kept', async ({ page }) => {
  await signInWithoutTheCookie(page)
  await expect(page.getByRole('alert')).toHaveText(
    'Signed in, but this browser did not keep the session. Allow cookies for this site, then ' +
      'sign in again.',
  )
  expect(page.url()).toContain('/login')
})

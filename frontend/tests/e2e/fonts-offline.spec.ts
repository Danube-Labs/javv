/**
 * Behind a firewall that drops outside traffic (issue 818), a request to another host is never
 * answered. An outside stylesheet then blocked the sign-in page for 21.8 s. Here every request to
 * another host is held forever, and the page must still show at once with both faces loaded.
 * The check reads the loaded FontFace list: `document.fonts.check()` answers true for a family
 * that was never declared, so it would pass with no font at all.
 */
import { BASE, expect, test } from './helpers'

const firstFamily = (stack: string) => stack.split(',')[0]!.trim().replace(/^['"]|['"]$/g, '')

test('the sign-in page shows at once with both faces when outside hosts never answer', async ({ page }) => {
  const app = new URL(BASE).host
  const held: string[] = []
  await page.route(
    (url) => url.host !== app,
    (route) => {
      held.push(new URL(route.request().url()).host) // never fulfilled: a dropped packet
    },
  )
  await page.goto(`${BASE}/login`, { waitUntil: 'commit' })
  await expect(page.locator('#username')).toBeVisible({ timeout: 5_000 })

  const wanted = await page.evaluate(() => {
    const css = getComputedStyle(document.documentElement)
    return [css.getPropertyValue('--font-ui'), css.getPropertyValue('--font-mono')]
  })
  const families = wanted.map(firstFamily)
  await expect
    .poll(
      () =>
        page.evaluate(() =>
          [...document.fonts].filter((f) => f.status === 'loaded').map((f) => f.family.replace(/^['"]|['"]$/g, '')),
        ),
      { timeout: 5_000 },
    )
    .toEqual(expect.arrayContaining(families))
  expect(held).toEqual([])
})

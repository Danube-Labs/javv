/**
 * Heading levels (issue 681): a screen reader user moves through a page by its headings, and a
 * title that jumps from the page's h1 to an h3 reads as a missing section. Walks every listed
 * route plus the two detail pages. Dialogs are opened on demand and are not part of the walk.
 */
import type { Page } from '@playwright/test'

// @ts-expect-error walk.mjs is the untyped shared walk module — the route owner
import { ROUTES } from '../../scripts/walk.mjs'
import { BASE, expect, login, test } from './helpers'

/** Every visible heading in <main> that sits more than one level below the one before it. */
async function skips(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const out: string[] = []
    let prev = 0
    for (const h of document.querySelectorAll('main h1, main h2, main h3, main h4, main h5, main h6')) {
      if ((h as HTMLElement).getBoundingClientRect().width === 0) continue
      const level = Number(h.tagName[1])
      if (prev && level > prev + 1) out.push(`h${prev} then h${level} "${h.textContent!.trim().slice(0, 40)}"`)
      prev = level
    }
    return out
  })
}

test('no screen skips a heading level', async ({ page }) => {
  test.setTimeout(180_000)
  await login(page)
  const found: string[] = []
  for (const route of ROUTES as { name: string; path: string; ready: string }[]) {
    await page.goto(`${BASE}${route.path}`)
    await page.waitForSelector(route.ready, { timeout: 20_000 })
    await page.waitForLoadState('networkidle')
    found.push(...(await skips(page)).map((s) => `${route.name}: ${s}`))
  }
  for (const [list, ready, name] of [['/findings', '.detail-head', 'finding detail'], ['/images', '.head-actions', 'image detail']]) {
    await page.goto(`${BASE}${list}`)
    await page.locator('.tbl tbody a.row-link').first().click({ timeout: 20_000 })
    await page.waitForSelector(ready!, { timeout: 15_000 })
    await page.waitForLoadState('networkidle')
    found.push(...(await skips(page)).map((s) => `${name}: ${s}`))
  }
  expect(found).toEqual([])
})

// issue 829: before the first cluster, nine routes show only the cold-start state, whose title
// was an h2 with no h1 above it
test('the cold-start screen has its one h1 on every route that shows it', async ({ page }) => {
  test.setTimeout(120_000)
  await page.route(
    (url) => url.pathname === '/api/v1/clusters',
    (route) => route.fulfill({ json: { clusters: [] } }),
  )
  await login(page)
  const wrong: string[] = []
  for (const path of ['/overview', '/findings', '/images', '/scanner-status', '/clusters', '/audit', '/contributors', '/approvals', '/views']) {
    await page.goto(`${BASE}${path}`)
    await page.getByText('No clusters registered yet').waitFor({ timeout: 20_000 })
    const h1s = await page.locator('main h1').allTextContents()
    if (h1s.length !== 1 || h1s[0]!.trim() !== 'No clusters registered yet') wrong.push(`${path}: ${JSON.stringify(h1s)}`)
  }
  expect(wrong).toEqual([])
})

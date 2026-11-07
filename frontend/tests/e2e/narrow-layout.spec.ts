/**
 * Layout at the 1024 design floor (issue 667). jsdom has no layout, so only a browser can prove
 * that one box does not sit on another or push the page sideways.
 */

import { BASE, expect, login, test } from './helpers'

test.use({ viewport: { width: 1024, height: 800 } })

test.beforeEach(async ({ page }) => {
  await login(page)
})

test('Settings: a section tab shows its whole label, with the scope dot beside it', async ({ page }) => {
  await page.goto(`${BASE}/settings`)
  await expect(page.locator('.snav-item').first()).toBeVisible({ timeout: 20_000 })
  const overlaps = await page.evaluate(() =>
    [...document.querySelectorAll('.snav-item')].map((item) => {
      const label = item.querySelector('span')!.getBoundingClientRect()
      const dot = item.querySelector('.scope-dot')!.getBoundingClientRect()
      return { tab: item.textContent!.trim(), overlap: Math.round(label.right - dot.left) }
    }),
  )
  expect(overlaps.length).toBeGreaterThan(0)
  expect(overlaps.filter((o) => o.overlap > 0)).toEqual([])
})

test('Image detail: the page does not scroll sideways, and the scanner switch is on screen', async ({ page }) => {
  await page.goto(`${BASE}/images`)
  await page.locator('.tbl tbody a.row-link').first().click({ timeout: 20_000 })
  await expect(page.locator('.head-actions')).toBeVisible({ timeout: 15_000 })
  await page.waitForLoadState('networkidle')
  const { doc, win, switchRight } = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    win: window.innerWidth,
    switchRight: Math.round(document.querySelector('.head-actions')!.getBoundingClientRect().right),
  }))
  expect(doc).toBeLessThanOrEqual(win)
  expect(switchRight).toBeLessThanOrEqual(win)
})

test.describe('at 1366, the common laptop width', () => {
  test.use({ viewport: { width: 1366, height: 800 } })

  test('Findings: the ingest strip subtitle shows its whole sentence', async ({ page }) => {
    await page.goto(`${BASE}/findings`)
    const sub = page.locator('.ingest-lens .il-sub')
    await expect(sub).toBeVisible({ timeout: 20_000 })
    await expect(sub).toContainText('of this range')
    const { needs, has } = await sub.evaluate((el) => ({ needs: el.scrollWidth, has: el.clientWidth }))
    expect(needs).toBeLessThanOrEqual(has)
  })

  test('Top bar: the search hint shows its whole text', async ({ page }) => {
    await page.goto(`${BASE}/findings`)
    const hint = page.locator('.gs-hint')
    await expect(hint).toBeVisible({ timeout: 20_000 })
    const { needs, has } = await hint.evaluate((el) => ({ needs: el.scrollWidth, has: el.clientWidth }))
    expect(needs).toBeLessThanOrEqual(has)
  })
})

// issue 1115: at 1440 the MCP token table was 966 px in a card of 904 px, so the Revoke buttons
// were out of view. The MCP list comes from here (the tokens of the 1110 test and a name of the
// longest length), so the store keeps no new tokens; Access & tokens reads the seeded ones.
const DAY_MS = 86_400_000
function mcpTokens(now: number) {
  const names = ['e2e-read', 'e2e-write', 'e2e-risk', 'e2e-made-while-off', 'e2e-expired', 'e2e-revoked']
  return [...names, `agent-${'x'.repeat(58)}`].map((name, i) => ({
    name,
    level: ['read', 'write', 'write_risk_accept'][i % 3],
    created_by: 'admin',
    created_at: new Date(now - (3 + i) * DAY_MS).toISOString(),
    expiry: new Date(now + (name === 'e2e-expired' ? -1 : 30) * DAY_MS).toISOString(),
    disabled: name === 'e2e-revoked',
    last_used_at: i % 2 ? new Date(now - 3_600_000).toISOString() : null,
  }))
}

/** How far the table is wider than the box that holds it, and the buttons past the box's edge. */
async function tokenTableFit(page: import('@playwright/test').Page) {
  await page.locator('.tbl tbody tr').first().waitFor({ timeout: 20_000 })
  return page.evaluate(() => {
    const table = document.querySelector('.tbl')!
    const box = table.parentElement!
    const edge = box.getBoundingClientRect().right
    const buttons = [...table.querySelectorAll('tbody button')]
    return {
      over: Math.round(table.getBoundingClientRect().width) - box.clientWidth,
      buttons: buttons.length,
      outside: buttons.filter((b) => b.getBoundingClientRect().right > edge + 0.5).length,
    }
  })
}

for (const width of [1366, 1440, 1920]) {
  test.describe(`token tables at ${width}`, () => {
    test.use({ viewport: { width, height: 900 } })

    test('Settings, AI agents (MCP): the table fits its card, with each button in view', async ({ page }) => {
      const tokens = mcpTokens(Date.now())
      await page.route(
        (url) => url.pathname === '/api/v1/admin/mcp-tokens',
        (route) => route.fulfill({ json: { tokens, total: tokens.length } }),
      )
      await page.goto(`${BASE}/settings/ai-agents`)
      const fit = await tokenTableFit(page)
      expect(fit.buttons).toBeGreaterThan(0)
      expect(fit).toEqual({ over: 0, buttons: fit.buttons, outside: 0 })
    })

    test('Settings, Access & tokens: the table fits its card, with each button in view', async ({ page }) => {
      await page.goto(`${BASE}/settings/tokens`)
      const fit = await tokenTableFit(page)
      expect(fit.buttons).toBeGreaterThan(0)
      expect(fit).toEqual({ over: 0, buttons: fit.buttons, outside: 0 })
    })
  })
}

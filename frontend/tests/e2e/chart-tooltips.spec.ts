/**
 * The chart tooltips under the policy of the frontend server (issue 1272). The policy refused the
 * style attributes of the old ECharts tooltips, so a deployed JAVV showed bare text with no dots.
 * This spec moves the pointer over each chart and reads each row of the tooltip. The fixture of
 * `helpers.ts` fails the test on a policy violation. The spec skips on a server that sends no
 * policy, and fails in CI.
 */
import type { Locator, Page } from '@playwright/test'

import { BASE, expect, login, requirePolicy, test } from './helpers'

/** Moves the pointer along the middle of a chart until its tooltip shows, then gives the tooltip. */
async function tooltipOf(page: Page, chart: Locator): Promise<Locator> {
  const box = await chart.boundingBox()
  if (!box) throw new Error('the chart has no box on screen')
  const tip = page.locator('.chart-tip').filter({ visible: true })
  for (let i = 1; i < 30; i++) {
    await page.mouse.move(box.x + (box.width * i) / 30, box.y + box.height / 2)
    if ((await tip.count()) > 0) return tip.first()
  }
  throw new Error('no tooltip showed along the middle of the chart')
}

/** Each row of a tooltip has a dot that the eye can see: a size and a color. */
async function expectRowsWithDots(tip: Locator): Promise<void> {
  const rows = tip.locator('.chart-tip-row')
  expect(await rows.count()).toBeGreaterThan(0)
  for (const dot of await tip.locator('.chart-tip-dot').all()) {
    const look = await dot.evaluate((d) => {
      const s = getComputedStyle(d)
      return { width: d.getBoundingClientRect().width, color: s.backgroundColor }
    })
    expect(look.width).toBeGreaterThanOrEqual(8)
    expect(look.color).not.toBe('rgba(0, 0, 0, 0)')
  }
  expect(await tip.locator('.chart-tip-dot').count()).toBe(await rows.count())
}

/** Moves the pointer off the charts, so the next chart shows its own tooltip. */
const away = (page: Page) => page.mouse.move(2, 2)

test.beforeEach(async ({ page }) => {
  await requirePolicy(page)
  await login(page)
})

test('each chart of the Overview shows its tooltip with a dot in each row', async ({ page }) => {
  await page.goto(`${BASE}/overview`)
  const charts = page.locator('canvas')
  // the seed gives the scan ingest strip and the trend chart at least
  await expect.poll(() => charts.count(), { timeout: 15_000 }).toBeGreaterThanOrEqual(2)
  for (const chart of await charts.all()) {
    await away(page)
    await expectRowsWithDots(await tooltipOf(page, chart))
  }

  await page.getByRole('button', { name: 'by severity' }).click()
  await away(page)
  await expectRowsWithDots(await tooltipOf(page, charts.nth(1)))
})

test('the strip of the Audit log shows its tooltip with a dot', async ({ page }) => {
  await page.goto(`${BASE}/audit`)
  const chart = page.locator('canvas').first()
  await expect(chart).toBeVisible({ timeout: 15_000 })
  await expectRowsWithDots(await tooltipOf(page, chart))
})

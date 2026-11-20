/**
 * The chart tooltips under the policy of the frontend server (issue 1272). The policy refused the
 * style attributes of the old ECharts tooltips, so a deployed JAVV showed bare text with no dots.
 * This spec moves the pointer over each chart and reads each row of the tooltip. The fixture of
 * `helpers.ts` fails the test on a policy violation. The spec skips on a server that sends no
 * policy, and fails in CI.
 */
import type { Locator, Page } from '@playwright/test'

import { BASE, expect, login, requirePolicy, test } from './helpers'

/** What a tooltip shows: its rows, and the size and the color of each dot. */
interface TipLook {
  rows: number
  dots: { width: number; color: string }[]
}

/** Moves the pointer along the middle of a chart until the tooltip of that chart shows, and reads
 *  it in one step. ECharts puts the tooltip in the root of its chart (`.echarts-host`). The
 *  tooltip of the chart before it can still fade out somewhere on the page, so the spec reads
 *  only the root of this chart. */
async function tooltipOf(page: Page, chart: Locator): Promise<TipLook> {
  const box = await chart.boundingBox()
  if (!box) throw new Error('the chart has no box on screen')
  const tip = chart.locator('xpath=ancestor::*[contains(@class, "echarts-host")][1]').locator('.chart-tip')
  for (let i = 1; i < 30; i++) {
    await page.mouse.move(box.x + (box.width * i) / 30, box.y + box.height / 2)
    const shown = await tip.filter({ visible: true }).evaluateAll((tips) =>
      tips.map((t) => ({
        rows: t.querySelectorAll('.chart-tip-row').length,
        dots: [...t.querySelectorAll('.chart-tip-dot')].map((d) => ({
          width: d.getBoundingClientRect().width,
          color: getComputedStyle(d).backgroundColor,
        })),
      })),
    )
    if (shown.length) return shown[0]!
  }
  throw new Error('no tooltip showed along the middle of the chart')
}

/** Each row of a tooltip has a dot that the eye can see: a size and a color. */
function expectRowsWithDots(tip: TipLook): void {
  expect(tip.rows).toBeGreaterThan(0)
  expect(tip.dots).toHaveLength(tip.rows)
  for (const dot of tip.dots) {
    expect(dot.width).toBeGreaterThanOrEqual(8)
    expect(dot.color).not.toBe('rgba(0, 0, 0, 0)')
  }
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

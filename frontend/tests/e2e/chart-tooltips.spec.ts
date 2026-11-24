/**
 * The chart tooltips under the policy of the frontend server (issue 1272). The policy refused the
 * style attributes of the old ECharts tooltips, so a deployed JAVV showed bare text with no dots.
 * This spec moves the pointer over each chart and reads each row of the tooltip. The fixture of
 * `helpers.ts` fails the test on a policy violation. The spec skips on a server that sends no
 * policy, and fails in CI.
 */
import type { Locator, Page } from '@playwright/test'

import { BASE, expect, login, requirePolicy, test } from './helpers'

/** What a tooltip shows: its rows, the name of each row, and the size and the color of each dot. */
interface TipLook {
  /** The head line: the axis label, and the unit when the chart gives one. */
  head: string
  rows: number
  names: string[]
  dots: { width: number; color: string }[]
  /** The font of the first name and of the first value. */
  fonts: { name: string; value: string }
}

/** The names of the rows of the severity chart: the six canonical severities. */
const SEVERITY_NAMES = ['critical', 'high', 'medium', 'low', 'negligible', 'unknown']

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
        head: t.querySelector('.chart-tip-head')?.textContent ?? '',
        rows: t.querySelectorAll('.chart-tip-row').length,
        names: [...t.querySelectorAll('.chart-tip-name')].map((n) => n.textContent ?? ''),
        fonts: {
          name: getComputedStyle(t.querySelector('.chart-tip-name') ?? t).fontFamily,
          value: getComputedStyle(t.querySelector('.chart-tip-val') ?? t).fontFamily,
        },
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

/** Each row of a tooltip has a dot that the eye can see: a size and a color. The name is in the
 *  UI font and the value in the mono font, as each count of the app. ECharts writes its own font
 *  on the box (issue 1275). */
function expectRowsWithDots(tip: TipLook): void {
  expect(tip.rows).toBeGreaterThan(0)
  expect(tip.fonts.name).toContain('Hanken Grotesk')
  expect(tip.fonts.value).toContain('Spline Sans Mono')
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

  // The card shows a note in place of its chart while the severity data loads, or when it has
  // none. So the step reads the chart in this card only, and each row must be a severity.
  const trend = page.locator('section.card', {
    has: page.getByRole('heading', { name: 'Vulnerabilities over time' }),
  })
  await trend.getByRole('button', { name: 'by severity' }).click()
  const severityChart = trend.locator('canvas')
  await expect(severityChart).toBeVisible({ timeout: 15_000 })
  await away(page)
  const tip = await tooltipOf(page, severityChart)
  expectRowsWithDots(tip)
  for (const name of tip.names) expect(SEVERITY_NAMES).toContain(name)
})

test('the strip of the Audit log shows its tooltip with a dot', async ({ page }) => {
  await page.goto(`${BASE}/audit`)
  const chart = page.locator('canvas').first()
  await expect(chart).toBeVisible({ timeout: 15_000 })
  const tip = await tooltipOf(page, chart)
  expectRowsWithDots(tip)
  // a chart with no unit shows the axis label alone: ECharts calls the formatter with a random
  // ticket as its second argument, and that ticket once showed after the label (issue 1292)
  expect(tip.head).toMatch(/\S/)
  expect(tip.head).not.toContain(' · ')
})

test('the New findings strip on Findings shows its hover with the unit and a dot in each row (issue 1292)', async ({ page }) => {
  await page.goto(`${BASE}/findings`)
  const strip = page.locator('.lens-stack .ingest-lens').nth(1)
  await expect(strip.locator('.il-title')).toHaveText('New findings', { timeout: 15_000 })
  const chart = strip.locator('canvas')
  await expect(chart).toBeVisible({ timeout: 15_000 })
  await away(page)
  const tip = await tooltipOf(page, chart)
  expectRowsWithDots(tip)
  expect(tip.head).toMatch(/ · new findings$/)
})

test('the hover of a strip in the joined band shows whole, with its unit (issue 1292)', async ({ page }) => {
  // The band of Scanner status clipped its strips (overflow: hidden). The hover box of Scan ingest
  // rises above the top of the band, so the band cut off its head line, the time and the unit.
  await page.goto(`${BASE}/scanner-status`)
  const band = page.locator('.lens-stack')
  const chart = band.locator('.ingest-lens').first().locator('canvas')
  await expect(chart).toBeVisible({ timeout: 15_000 })
  await away(page)
  expectRowsWithDots(await tooltipOf(page, chart))
  const tip = chart.locator('xpath=ancestor::*[contains(@class, "echarts-host")][1]').locator('.chart-tip')
  const look = await tip.filter({ visible: true }).first().evaluate((t) => {
    // ECharts gives its box `pointer-events: none`, so a hit test passes through it. The check
    // reads the clip of each ancestor instead (overflow, clip-path or paint containment): such an
    // ancestor that does not hold the whole head line cuts that line off.
    const head = (t.querySelector('.chart-tip-head') ?? t).getBoundingClientRect()
    const cutBy: string[] = []
    for (let node = t.parentElement; node && node !== document.body; node = node.parentElement) {
      const style = getComputedStyle(node)
      const clips =
        style.overflowY !== 'visible' ||
        style.overflowX !== 'visible' ||
        style.clipPath !== 'none' ||
        /paint|strict|content/.test(style.contain)
      if (!clips) continue
      const r = node.getBoundingClientRect()
      if (r.top > head.top || r.bottom < head.bottom || r.left > head.left || r.right < head.right)
        cutBy.push(`${node.tagName.toLowerCase()}.${[...node.classList].join('.')}`)
    }
    return { head: t.querySelector('.chart-tip-head')?.textContent ?? '', cutBy }
  })
  expect(look.head).toMatch(/ · images scanned$/)
  // no ancestor of the hover box cuts off its head line
  expect(look.cutBy).toEqual([])
})

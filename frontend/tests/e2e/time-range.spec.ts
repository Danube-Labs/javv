/**
 * The strips draw the hours of the backend for a short range (issue 1291). The backend counts the
 * range back from its own clock, and the strips take that clock from the `Date` header of each
 * API response. So a browser clock that is 40 minutes ahead or behind gives the same bars as a
 * right one. The spec reads only: it answers the scans read of the Scan ingest strip itself, at the
 * hour of now and the hour before, and reads the head of the hover of each bar.
 */
import type { Page } from '@playwright/test'

import { BASE, expect, login, test } from './helpers'

const HOUR = 3_600_000

/** The hour label of the strips (`hourLabel` of `charts/buildIngestLensOption.ts`), in the time
 *  zone of the browser. */
async function hourLabel(page: Page, ms: number): Promise<string> {
  return page.evaluate(
    (t) => new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false }),
    ms,
  )
}

/** The heads of the hover along the middle of a chart: one for each bar that has a count. */
async function hoverHeads(page: Page): Promise<string[]> {
  const strip = page.locator('.lens-stack .ingest-lens').first()
  const chart = strip.locator('canvas')
  await expect(chart).toBeVisible({ timeout: 15_000 })
  const box = await chart.boundingBox()
  if (!box) throw new Error('the chart has no box on screen')
  const tip = strip.locator('.chart-tip')
  const heads = new Set<string>()
  for (let i = 1; i < 40; i++) {
    await page.mouse.move(box.x + (box.width * i) / 40, box.y + box.height / 2)
    for (const head of await tip.filter({ visible: true }).locator('.chart-tip-head').allTextContents()) {
      heads.add(head)
    }
  }
  return [...heads]
}

for (const [name, minutes] of [
  ['right', 0],
  ['40 minutes ahead', 40],
  ['40 minutes behind', -40],
] as const) {
  test(`Last 1 hour with a browser clock ${name} shows the hours of the backend`, async ({ page }) => {
    await login(page)
    // this machine runs the backend, so its clock is the clock of the backend
    const now = Date.now()
    const thisHour = Math.floor(now / HOUR) * HOUR
    const sent: URL[] = []
    await page.route('**/api/v1/trends/scans?*', async (route) => {
      sent.push(new URL(route.request().url()))
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { date: new Date().toUTCString() },
        body: JSON.stringify({
          series: {
            trivy: [
              { date: new Date(thisHour - HOUR).toISOString(), scans: 2 },
              { date: new Date(thisHour).toISOString(), scans: 3 },
            ],
          },
          days: null,
          window_seconds: 3600,
          interval: 'hour',
        }),
      })
    })
    await page.clock.install({ time: now + minutes * 60_000 })
    await page.goto(`${BASE}/findings?win=0.0417`)

    const heads = (await hoverHeads(page)).sort()
    const expected = async (hour: number) =>
      [`${await hourLabel(page, hour - HOUR)} · images scanned`, `${await hourLabel(page, hour)} · images scanned`].sort()
    // a run that starts just before the hour can draw on the next hour: its axis then has the
    // hour of the answer and the next hour, and the hour before is not on it
    const endHour = Math.floor(Date.now() / HOUR) * HOUR
    if (endHour === thisHour) expect(heads).toEqual(await expected(thisHour))
    else expect(heads).toContain(`${await hourLabel(page, thisHour)} · images scanned`)
    // the browser sends only the length of the range, never a time of its own clock
    const query = sent.at(-1)!.searchParams
    expect(query.get('window_seconds')).toBe('3600')
    expect(query.has('days')).toBe(false)
  })
}

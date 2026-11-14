/**
 * The day labels under the x axis of the four day charts (issue 1190, row 14): the day and the
 * short month in the time zone of the browser, as `3 Nov`.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { buildAuditLensOption } from '@/charts/buildAuditLensOption'
import { buildFindingsTrendOption } from '@/charts/buildFindingsTrendOption'
import { buildScanActivityOption } from '@/charts/buildScanActivityOption'
import { buildSeverityTrendOption } from '@/charts/buildSeverityTrendOption'
import { dayLabel } from '@/lib/format'

// Node reads TZ again when it changes, so a test can play a browser in another zone.
const zone = process.env.TZ
afterEach(() => {
  // a plain assignment of undefined would set the text "undefined"
  if (zone === undefined) delete process.env.TZ
  else process.env.TZ = zone
})

// 20:00 UTC on 3 November is already 4 November in Tokyo (UTC+9).
const DATES = ['2026-11-03T00:00:00Z', '2026-11-03T20:00:00Z']

const axisOf = (option: { xAxis?: unknown }): unknown => (option.xAxis as { data: unknown }).data

const builders: Record<string, () => unknown> = {
  'findings trend': () =>
    axisOf(
      buildFindingsTrendOption({
        new: { trivy: DATES.map((date) => ({ date, count: 1 })) },
        resolved: {},
      }),
    ),
  'severity trend': () =>
    axisOf(buildSeverityTrendOption({ high: DATES.map((date) => ({ date, count: 1 })) })),
  'audit lens': () => axisOf(buildAuditLensOption(DATES.map((date) => ({ date, count: 1 })))),
  'scan activity': () =>
    axisOf(buildScanActivityOption({ grype: DATES.map((date) => ({ date, scans: 1 })) })),
}

describe('day labels on the chart axis', () => {
  it('dayLabel writes the day and the short month', () => {
    process.env.TZ = 'UTC'
    expect(DATES.map(dayLabel)).toEqual(['3 Nov', '3 Nov'])
    process.env.TZ = 'Asia/Tokyo'
    expect(DATES.map(dayLabel)).toEqual(['3 Nov', '4 Nov'])
  })

  it.each(Object.keys(builders))('%s: the day and the short month', (name) => {
    process.env.TZ = 'UTC'
    expect(builders[name]!()).toEqual(['3 Nov', '3 Nov'])
  })

  it.each(Object.keys(builders))('%s: the day in the time zone of the browser', (name) => {
    process.env.TZ = 'Asia/Tokyo'
    expect(builders[name]!()).toEqual(['3 Nov', '4 Nov'])
  })
})

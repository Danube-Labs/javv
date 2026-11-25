/** The range of a trend read and the axis of a strip (issue 1291): a range of 2 days or less at now
 * is exact, a longer range or a past T is in whole UTC days. */
import { afterEach, describe, expect, it } from 'vitest'

import { hourLabel, stripAxis } from '@/charts/buildIngestLensOption'
import { buildDailyTrendQuery, buildTrendQuery, exactWindowSeconds, newInRange } from '@/charts/buildTrendQuery'

const HOUR = 1 / 24
const NOW = Date.parse('2026-11-20T10:31:00Z')
const PAST = '2026-11-18T12:00:00Z'

describe('exactWindowSeconds', () => {
  it.each([
    ['Last 30 minutes', 30 / 1440, 1800],
    ['Last 1 hour as the URL keeps it (win=0.0417 is 1 hour and 3 seconds)', 0.0417, 3600],
    ['Last 24 hours', 1, 86_400],
    ['exactly 2 days', 2, 172_800],
    ['less than one minute', 0.0001, 60],
  ])('%s: whole minutes', (_name, windowDays, seconds) => {
    expect(exactWindowSeconds(windowDays, null)).toBe(seconds)
  })

  it('2 days and 1 second is in whole days', () => {
    expect(exactWindowSeconds(2 + 1 / 86_400, null)).toBeNull()
  })

  it('a past T is in whole days, also for a short range', () => {
    expect(exactWindowSeconds(HOUR, PAST)).toBeNull()
  })
})

describe('buildTrendQuery', () => {
  it('a short range at now sends its length and no days', () => {
    expect(buildTrendQuery('c-1', 0.0417, null)).toEqual({ cluster_id: 'c-1', window_seconds: 3600 })
  })

  it('a longer range sends whole days', () => {
    expect(buildTrendQuery('c-1', 2.5, null)).toEqual({ cluster_id: 'c-1', days: 3 })
  })

  it('a past T sends whole days and the time', () => {
    expect(buildTrendQuery('c-1', HOUR, PAST)).toEqual({ cluster_id: 'c-1', days: 1, as_of: PAST })
  })

  it('/trends/findings is daily only: a short range sends 1 day', () => {
    expect(buildDailyTrendQuery('c-1', HOUR, null)).toEqual({ cluster_id: 'c-1', days: 1 })
  })
})

describe('newInRange', () => {
  it('"New in range" takes the range of the strips, so the table and the strip count the same rows', () => {
    expect(newInRange(0.0417, null)).toEqual({ new_within_seconds: 3600 })
    expect(newInRange(7, null)).toEqual({ new_within_days: 7 })
    expect(newInRange(0.0417, PAST)).toEqual({ new_within_days: 1 })
  })
})

describe('stripAxis', () => {
  it('Last 1 hour at 10:31: the hours of 09:31 to 10:31, and no hour of the day before', () => {
    expect(stripAxis(HOUR, null, 'hour', NOW)).toEqual(['2026-11-20T09:00:00.000Z', '2026-11-20T10:00:00.000Z'])
  })

  it('a start on the hour: the first bucket is the hour of the start', () => {
    const now = Date.parse('2026-11-20T11:00:00Z')
    expect(stripAxis(HOUR, null, 'hour', now)).toEqual(['2026-11-20T10:00:00.000Z', '2026-11-20T11:00:00.000Z'])
  })

  it('exactly 2 days: 49 hours, from the hour of the start two days before', () => {
    const axis = stripAxis(2, null, 'hour', NOW)
    expect(axis).toHaveLength(49)
    expect(axis[0]).toBe('2026-11-18T10:00:00.000Z')
    expect(axis.at(-1)).toBe('2026-11-20T10:00:00.000Z')
  })

  it('2 days and 1 second: whole UTC days, as before', () => {
    expect(stripAxis(2 + 1 / 86_400, null, 'day', NOW)).toEqual([
      '2026-11-17T00:00:00.000Z',
      '2026-11-18T00:00:00.000Z',
      '2026-11-19T00:00:00.000Z',
      '2026-11-20T00:00:00.000Z',
    ])
  })

  it('a range across midnight UTC and the end of a month has no gap', () => {
    const now = Date.parse('2026-12-01T00:30:00Z')
    expect(stripAxis(HOUR, null, 'hour', now)).toEqual(['2026-11-30T23:00:00.000Z', '2026-12-01T00:00:00.000Z'])
  })

  it('a past T keeps the whole days of its end', () => {
    expect(stripAxis(HOUR, PAST, 'day', NOW)).toEqual(['2026-11-17T00:00:00.000Z', '2026-11-18T00:00:00.000Z'])
  })
})

// Node reads TZ again when it changes, so a test can play a browser in another zone.
const zone = process.env.TZ
afterEach(() => {
  // a plain assignment of undefined would set the text "undefined"
  if (zone === undefined) delete process.env.TZ
  else process.env.TZ = zone
})

describe('the labels of the hourly bars', () => {
  it('a browser in +05:30 shows the local times of the UTC bars', () => {
    process.env.TZ = 'Asia/Kolkata'
    expect(stripAxis(HOUR, null, 'hour', NOW).map(hourLabel)).toEqual(['14:30', '15:30'])
  })

  it('the summer-time change of Europe/Bucharest shows the hour 03:00 two times', () => {
    process.env.TZ = 'Europe/Bucharest'
    // 25 October 2026: 00:00 UTC is 03:00 summer time, 01:00 UTC is 03:00 winter time
    const now = Date.parse('2026-10-25T01:10:00Z')
    expect(stripAxis(2 * HOUR, null, 'hour', now).map(hourLabel)).toEqual(['02:00', '03:00', '03:00'])
  })
})

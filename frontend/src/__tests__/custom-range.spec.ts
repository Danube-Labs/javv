/** The length of an Exact range of the time picker (issue 1313, rulings Q1 A, Q2 A, Q3 A): a range
 * that ends now starts at its From time, and a range that ends in the past keeps whole days. The
 * cases check the length that the strips then send (`exactWindowSeconds`, `trendDays`). Now has
 * seconds and the fields have minutes only, as in the app. */
import { describe, expect, it } from 'vitest'

import { exactWindowSeconds, trendDays } from '@/charts/buildTrendQuery'
import { customRange } from '@/components/time-travel/customRange'

const NOW = Date.parse('2026-11-25T11:36:41Z')
const NOW_MINUTE = Date.parse('2026-11-25T11:36:00Z')
const MIN = 60_000
const H = 3_600_000
const DAY = 86_400_000

describe('an Exact range that ends now starts at its From time (Q1 A)', () => {
  it.each([
    ['2 hours', 2 * H, 7200],
    ['1.4 days', 1.4 * DAY, 120_960],
    ['exactly 2 days', 2 * DAY, 172_800],
  ])('%s sends its own length', (_name, length, seconds) => {
    const range = customRange(NOW_MINUTE - length, NOW_MINUTE, NOW)
    expect(range.endsNow).toBe(true)
    expect(exactWindowSeconds(range.days, null)).toBe(seconds)
  })

  it('a To time 59 seconds before now ends the range now, with its own length', () => {
    const range = customRange(NOW_MINUTE - 2 * H, NOW_MINUTE, NOW_MINUTE + 59_000)
    expect(range.endsNow).toBe(true)
    expect(exactWindowSeconds(range.days, null)).toBe(7200)
  })

  it('a To time 61 seconds before now ends in the past (the known gap of the 60 s)', () => {
    expect(customRange(NOW_MINUTE - 2 * H, NOW_MINUTE, NOW_MINUTE + 61_000).endsNow).toBe(false)
  })

  it('a To time later than now starts the range at From, to the minute of now', () => {
    // From 09:00, To 23:00, at 11:36:41: the range is 09:00 to 11:36, 2 h 36 min
    const range = customRange(Date.parse('2026-11-25T09:00:00Z'), Date.parse('2026-11-25T23:00:00Z'), NOW)
    expect(range.endsNow).toBe(true)
    expect(exactWindowSeconds(range.days, null)).toBe(2 * 3600 + 36 * 60)
  })

  it('a From time later than now gives the shortest range of the API, 1 minute', () => {
    // the picker refuses this range: the function still never stores 0 or less
    const range = customRange(NOW + H, NOW + 2 * H, NOW)
    expect(range.endsNow).toBe(true)
    expect(range.days).toBe(MIN / DAY)
    expect(exactWindowSeconds(range.days, null)).toBe(60)
  })
})

describe('the To time on either clock (ruling 2 of issue 1291)', () => {
  it.each([
    ['2 minutes behind', -2],
    ['40 minutes ahead', 40],
  ])('with a browser clock %s, 2 hours to the time of the browser end now and stay 2 hours', (_name, minutes) => {
    const browser = NOW + minutes * MIN
    const to = Math.floor(browser / MIN) * MIN
    const range = customRange(to - 2 * H, to, NOW, browser)
    expect(range.endsNow).toBe(true)
    expect(exactWindowSeconds(range.days, null)).toBe(7200)
  })

  it('with a browser clock 40 minutes ahead, 2 hours to the time of the backend end now too', () => {
    const range = customRange(NOW_MINUTE - 2 * H, NOW_MINUTE, NOW, NOW + 40 * MIN)
    expect(range.endsNow).toBe(true)
    expect(exactWindowSeconds(range.days, null)).toBe(7200)
  })
})

describe('an Exact range of more than 2 days that ends now rounds up to whole days (Q3 A)', () => {
  it('3.4 days count 4 days, as for Quick select', () => {
    const range = customRange(NOW_MINUTE - 3.4 * DAY, NOW_MINUTE, NOW)
    expect(exactWindowSeconds(range.days, null)).toBeNull()
    expect(trendDays(range.days)).toBe(4)
  })

  it.each([7, 30])('%i whole days stay %i days', (days) => {
    const range = customRange(NOW_MINUTE - days * DAY, NOW_MINUTE, NOW)
    expect(range.days).toBe(days)
    expect(trendDays(range.days)).toBe(days)
  })

  it('more than 365 days count 365 days', () => {
    expect(customRange(NOW_MINUTE - 400 * DAY, NOW_MINUTE, NOW).days).toBe(365)
  })
})

describe('an Exact range that ends in the past keeps whole days (Q2 A)', () => {
  it.each([
    ['7 days and 6.5 hours count 7 days', 7 * DAY + 6.5 * H, 7],
    ['2 hours count 1 day', 2 * H, 1],
    ['1.6 days count 2 days', 1.6 * DAY, 2],
    ['400 days count 365 days', 400 * DAY, 365],
  ])('%s', (_name, length, days) => {
    const to = NOW_MINUTE - 2 * MIN
    const range = customRange(to - length, to, NOW)
    expect(range.endsNow).toBe(false)
    expect(range.days).toBe(days)
  })
})

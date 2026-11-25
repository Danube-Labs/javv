/** The strips draw their axis on the clock of the backend (issue 1291, Q1 B): the `Date` header of
 * each API response gives the difference to the clock of the browser. */
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

import { client } from '@/api/client'
import { stripAxis } from '@/charts/buildIngestLensOption'
import { useBucketRewind } from '@/composables/useBucketRewind'
import { useStripAxis, useStripNow } from '@/composables/useStripNow'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { noteServerDate, serverNow } from '@/system/serverClock'

const SERVER = Date.parse('2026-11-20T10:31:00Z')
const MIN = 60_000
const httpDate = (ms: number) => new Date(ms).toUTCString()

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => {
  noteServerDate(httpDate(0), 0) // back to the clock of the browser
  vi.useRealTimers()
})

describe('serverNow', () => {
  it('is the clock of the browser before the first response', () => {
    expect(serverNow(SERVER)).toBe(SERVER)
  })

  it.each([
    ['40 minutes ahead', 40],
    ['40 minutes behind', -40],
  ])('a browser clock %s gives the time of the backend', (_name, minutes) => {
    const browser = SERVER + minutes * MIN
    noteServerDate(httpDate(SERVER), browser)
    expect(serverNow(browser)).toBe(SERVER)
  })

  it('keeps the last difference when a header is missing or not a date', () => {
    noteServerDate(httpDate(SERVER), SERVER + 40 * MIN)
    noteServerDate(null)
    noteServerDate('not a date')
    expect(serverNow(SERVER + 40 * MIN)).toBe(SERVER)
  })
})

describe('the clock of the strips', () => {
  it.each([
    ['ahead', 40],
    ['behind', -40],
  ])('a browser clock 40 minutes %s draws the axis of the backend for Last 1 hour', (_name, minutes) => {
    vi.useFakeTimers({ now: SERVER + minutes * MIN, toFake: ['Date', 'setInterval', 'clearInterval'] })
    noteServerDate(httpDate(SERVER))
    const scope = effectScope()
    const now = scope.run(() => useStripNow())!
    // the backend at 10:31 counts 09:31 to 10:31: the hours 09:00 and 10:00
    expect(stripAxis(0.0417, null, 'hour', now.value)).toEqual([
      '2026-11-20T09:00:00.000Z',
      '2026-11-20T10:00:00.000Z',
    ])
    scope.stop()
  })

  it('a bar click takes the bucket in progress on the clock of the backend', () => {
    vi.useFakeTimers({ now: SERVER - 40 * MIN, toFake: ['Date'] }) // the browser says 09:51
    noteServerDate(httpDate(SERVER))
    const tt = useTimeTravelStore()
    useBucketRewind()('2026-11-20T09:00:00.000Z', 'hour')
    // on the backend it is 10:31, so the 09:00 hour is over: its end is the new T
    expect(tt.t).toBe('2026-11-20T09:59:59.999Z')
  })
})

describe('the axis of a strip with an exact range', () => {
  const at = (hhmm: string) => Date.parse(`2026-11-20T${hhmm}:00Z`)
  const hours = (...hh: string[]) => hh.map((h) => `2026-11-20T${h}:00:00.000Z`)

  it.each([
    // the backend counts from now less the range, and its first bucket is the hour of that start
    ['Last 30 minutes at 10:45 starts at 10:15', 0.0208, '10:45', hours('10')],
    ['Last 30 minutes at 10:10 starts at 09:40', 0.0208, '10:10', hours('09', '10')],
    ['Last 90 minutes at 10:45 starts at 09:15', 0.0625, '10:45', hours('09', '10')],
    ['Last 1 minute at 10:45 starts at 10:44', 1 / 1440, '10:45', hours('10')],
  ])('%s', (_name, windowDays, hhmm, axis) => {
    vi.useFakeTimers({ now: at(hhmm), toFake: ['Date', 'setInterval', 'clearInterval'] })
    const scope = effectScope()
    const shown = scope.run(() => useStripAxis(() => [windowDays, null, 'hour']))!
    expect(shown.value).toEqual(axis)
    scope.stop()
  })

  it('drops the first hour when the start passes it, and keeps its array between', () => {
    vi.useFakeTimers({ now: at('10:28'), toFake: ['Date', 'setInterval', 'clearInterval'] })
    const scope = effectScope()
    const shown = scope.run(() => useStripAxis(() => [0.0208, null, 'hour']))!
    const first = shown.value
    expect(first).toEqual(hours('09', '10'))
    vi.advanceTimersByTime(60_000) // 10:29: the same buckets
    expect(shown.value).toBe(first)
    vi.advanceTimersByTime(60_000) // 10:30: the range starts at 10:00
    expect(shown.value).toEqual(hours('10'))
    scope.stop()
  })
})

describe('the API client', () => {
  it('keeps the difference that the Date header of a response gives', async () => {
    const browser = Date.now()
    const answer = new Response('{}', {
      status: 200,
      headers: { 'content-type': 'application/json', date: httpDate(browser + 40 * MIN) },
    })
    // Node's Request needs an absolute address; in the browser the page's origin is the base
    await client.get({ baseUrl: 'http://localhost', url: '/api/v1/clusters', fetch: () => Promise.resolve(answer) })
    const offset = serverNow(browser) - browser
    expect(offset).toBeGreaterThan(40 * MIN - 5_000) // whole seconds, and the time of the test
    expect(offset).toBeLessThanOrEqual(40 * MIN)
  })
})

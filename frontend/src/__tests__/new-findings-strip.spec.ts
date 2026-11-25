/**
 * The New findings strip (issue 1292): the findings first seen in each bucket, by severity, under
 * the filters of the screen. It sits under Scan ingest in one band, with the same range and the
 * same day or hour rule, and reads `GET /trends/new-findings` itself (DESIGN.md section 10).
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import type { BarSeriesOption, EChartsOption } from 'echarts'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'

import { stripAxis } from '@/charts/buildIngestLensOption'
import { buildNewFindingsStripOption, totalNew } from '@/charts/buildNewFindingsStripOption'
import type { TooltipParam } from '@/charts/chartTooltip'
import EChart from '@/components/charts/EChart.vue'
import NewFindingsStrip from '@/components/dashboards/NewFindingsStrip.vue'
import { useStripNow } from '@/composables/useStripNow'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { CHART_SEV } from '@/styles/tokens'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    newFindingsTrendApiV1TrendsNewFindingsGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { newFindingsTrendApiV1TrendsNewFindingsGet } from '@/api/generated'

import { okWithoutBody } from './helpers/okWithoutBody'

const trendMock = vi.mocked(newFindingsTrendApiV1TrendsNewFindingsGet)
// each test unmounts its strips, so the shared band clock stops and the next test starts it
// with its own timers
enableAutoUnmount(afterEach)
const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
const NOW = new Date('2026-09-22T10:30:00Z').getTime()
const day = (d: number) => `2026-09-${String(d).padStart(2, '0')}T00:00:00.000Z`

describe('stripAxis (pure): the buckets of the range, as the backend counts them', () => {
  it('a daily range runs from the day floor of the start to the day of the end', () => {
    expect(stripAxis(2, null, 'day', NOW)).toEqual([day(20), day(21), day(22)])
    // a rewound end: the days up to the day of T
    expect(stripAxis(2, '2026-09-10T15:00:00.000Z', 'day', NOW)).toEqual([day(8), day(9), day(10)])
    // a range under one day still asks for one day, as buildTrendQuery does
    expect(stripAxis(0.25, null, 'day', NOW)).toEqual([day(21), day(22)])
  })

  it('an hourly range runs to the hour of now, so two strips of the band have one axis', () => {
    const axis = stripAxis(1, null, 'hour', NOW)
    // the exact range (issue 1291): from the hour of now less 24 hours
    expect(axis[0]).toBe('2026-09-21T10:00:00.000Z')
    expect(axis.at(-1)).toBe('2026-09-22T10:00:00.000Z')
    expect(axis).toHaveLength(25)
  })
})

describe('buildNewFindingsStripOption (pure)', () => {
  const axis = [day(20), day(21), day(22)]

  it('stacks one bar for each bucket, critical at the bottom, each in its severity color', () => {
    const option = buildNewFindingsStripOption(
      {
        low: [{ date: day(21), count: 2 }],
        critical: [
          { date: day(20), count: 1 },
          { date: day(22), count: 4 },
        ],
      },
      axis,
      'day',
    )
    const series = option.series as BarSeriesOption[]
    expect(series.map((s) => s.name)).toEqual(['critical', 'low']) // the order of SEVERITIES
    expect(series.every((s) => s.stack === 'new')).toBe(true)
    expect(series[0]!.itemStyle?.color).toBe(CHART_SEV.critical)
    // each count sits at its own date of the axis; a missing date is 0
    expect(series[0]!.data).toEqual([1, 0, 4])
    expect(series[1]!.data).toEqual([0, 2, 0])
    expect((option.xAxis as { data: string[] }).data).toHaveLength(3)
  })

  it('the hover says new findings, with a row for each severity', () => {
    const option = buildNewFindingsStripOption({ high: [{ date: day(21), count: 2 }] }, axis, 'day')
    const format = (option.tooltip as { formatter: (p: TooltipParam[]) => HTMLElement }).formatter
    const tip = format([{ axisValueLabel: '21 Sep', seriesName: 'high', value: 2 }])
    expect(tip.querySelector('.chart-tip-head')?.textContent).toBe('21 Sep · new findings')
  })

  it('hourly buckets get hour labels; whole counts only on the y axis', () => {
    const option = buildNewFindingsStripOption({}, ['2026-09-22T09:00:00.000Z'], 'hour')
    expect((option.xAxis as { data: string[] }).data).toHaveLength(1)
    expect((option.yAxis as { minInterval: number }).minInterval).toBe(1)
  })

  it('the total adds every severity and bucket', () => {
    expect(totalNew({ high: [{ date: day(21), count: 2 }], low: [{ date: day(20), count: 3 }] })).toBe(5)
    expect(totalNew({})).toBe(0)
  })
})

const props = { clusterId: 'c-k3d-0001', t: null, windowDays: 30, filters: {} }
const stubs = { EChart: true }

describe('NewFindingsStrip (self-contained)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })
  afterEach(() => vi.useRealTimers())

  it('asks for the Scan ingest window with the filters of the screen, and draws the bars', async () => {
    vi.useFakeTimers({ now: NOW, toFake: ['Date'] }) // 21 Sep is in the range of 30 days
    trendMock.mockResolvedValue(ok({ series: { high: [{ date: day(21), count: 2 }] } }))
    const w = mount(NewFindingsStrip, {
      props: { ...props, filters: { scanner: 'trivy', severity: ['high'], tag: ['1.4.1'] } },
      global: { stubs },
    })
    await flushPromises()
    expect(trendMock.mock.calls[0]![0]).toMatchObject({
      query: {
        cluster_id: 'c-k3d-0001',
        days: 30,
        interval: 'day',
        scanner: 'trivy',
        severity: ['high'],
        tag: ['1.4.1'],
      },
    })
    const option = w.findComponent(EChart).props('option') as EChartsOption
    const data = (option.series as BarSeriesOption[])[0]!.data as number[]
    expect(data.reduce((a, b) => a + b, 0)).toBe(2) // the bar is on the axis, not only in the total
    expect(w.text()).toContain('2 in this range')
  })

  it('a host that passes an equal new filter object on each render does not read again', async () => {
    trendMock.mockResolvedValue(ok({ series: {} }))
    const w = mount(NewFindingsStrip, { props: { ...props, filters: { scanner: 'trivy' } }, global: { stubs } })
    await flushPromises()
    for (let i = 0; i < 5; i++) await w.setProps({ filters: { scanner: 'trivy' } })
    await flushPromises()
    expect(trendMock).toHaveBeenCalledTimes(1)
    await w.setProps({ filters: { scanner: 'grype' } })
    await flushPromises()
    expect(trendMock).toHaveBeenCalledTimes(2)
  })

  it('a live read sends no as_of, also when the screen query holds one', async () => {
    trendMock.mockResolvedValue(ok({ series: {} }))
    mount(NewFindingsStrip, { props: { ...props, filters: { as_of: '2026-01-01T00:00:00Z' } }, global: { stubs } })
    await flushPromises()
    expect((trendMock.mock.calls[0]![0] as { query: Record<string, unknown> }).query).not.toHaveProperty('as_of')
  })

  it('the axis runs to the hour of the band clock, also with no new read, and a later read lands on it', async () => {
    vi.useFakeTimers({ now: NOW, toFake: ['Date', 'setInterval', 'clearInterval'] }) // 10:30
    trendMock.mockResolvedValue(ok({ series: { low: [{ date: '2026-09-22T05:00:00.000Z', count: 1 }] } }))
    const w = mount(NewFindingsStrip, { props: { ...props, windowDays: 1 }, global: { stubs } })
    await flushPromises()
    const labels = () => ((w.findComponent(EChart).props('option') as EChartsOption).xAxis as { data: string[] }).data
    expect(labels()).toHaveLength(25) // 21 Sep 10:00 to 22 Sep 10:00
    const first = labels()[0]
    vi.advanceTimersByTime(165 * 60_000) // 13:15: the band clock moves each minute
    await flushPromises()
    // to 13:00 with no new read, as Scan ingest above: the exact range moves with its end
    expect(labels()).toHaveLength(25)
    expect(labels()[0]).not.toBe(first)
    trendMock.mockResolvedValue(ok({ series: { high: [{ date: '2026-09-22T12:00:00.000Z', count: 5 }] } }))
    await w.setProps({ filters: { scanner: 'grype' } })
    await flushPromises()
    const option = w.findComponent(EChart).props('option') as EChartsOption
    const data = (option.series as BarSeriesOption[])[0]!.data as number[]
    expect(data.at(-2)).toBe(5) // the 12:00 bar, drawn where the total counts it
  })

  it('while a new range loads, the old bars stay on the axis of their own range', async () => {
    vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
    trendMock.mockResolvedValueOnce(ok({ series: { high: [{ date: day(21), count: 2 }] } }))
    const w = mount(NewFindingsStrip, { props, global: { stubs } })
    await flushPromises()
    trendMock.mockReturnValueOnce(new Promise(() => {}) as never) // the 24-hour read never lands
    await w.setProps({ windowDays: 1 })
    await flushPromises()
    const option = w.findComponent(EChart).props('option') as EChartsOption
    expect((option.series as BarSeriesOption[])[0]!.data).toHaveLength(31) // still the 30 days
  })

  it('leaves out the globals and New in range of the screen query: the strip has its own', async () => {
    trendMock.mockResolvedValue(ok({ series: {} }))
    mount(NewFindingsStrip, {
      props: {
        ...props,
        t: '2026-09-20T23:59:59.999Z',
        filters: { cluster_id: 'other', as_of: '2026-01-01T00:00:00Z', new_within_days: 30, kev: true },
      },
      global: { stubs },
    })
    await flushPromises()
    const query = (trendMock.mock.calls[0]![0] as { query: Record<string, unknown> }).query
    expect(query).toMatchObject({ cluster_id: 'c-k3d-0001', as_of: '2026-09-20T23:59:59.999Z', kev: true })
    expect(query).not.toHaveProperty('new_within_days')
  })

  it('leaves out the exact New in range too (issue 1291)', async () => {
    trendMock.mockResolvedValue(ok({ series: {} }))
    mount(NewFindingsStrip, {
      props: { ...props, windowDays: 0.0417, filters: { cluster_id: 'c-k3d-0001', new_within_seconds: 3600, kev: true } },
      global: { stubs },
    })
    await flushPromises()
    const query = (trendMock.mock.calls[0]![0] as { query: Record<string, unknown> }).query
    expect(query).toEqual({ cluster_id: 'c-k3d-0001', kev: true, window_seconds: 3600, interval: 'hour' })
  })

  it('a short live range buckets hourly; a rewound one is daily, as Scan ingest', async () => {
    trendMock.mockResolvedValue(ok({ series: {} }))
    const w = mount(NewFindingsStrip, { props: { ...props, windowDays: 1 }, global: { stubs } })
    await flushPromises()
    // the exact range of issue 1291: the length of the range, and no days
    expect(trendMock.mock.calls[0]![0].query).toMatchObject({ window_seconds: 86_400, interval: 'hour' })
    expect(trendMock.mock.calls[0]![0].query).not.toHaveProperty('days')
    expect(w.text()).toContain('each hour')
    await w.setProps({ t: '2026-09-20T23:59:59.999Z' })
    await flushPromises()
    expect(trendMock.mock.calls[1]![0]).toMatchObject({ query: { interval: 'day' } })
  })

  it('a range with no new findings is text, never an empty chart', async () => {
    trendMock.mockResolvedValue(ok({ series: {} }))
    const w = mount(NewFindingsStrip, { props, global: { stubs } })
    await flushPromises()
    expect(w.findComponent(EChart).exists()).toBe(false)
    expect(w.text()).toContain('No new findings in this range.')
  })

  it('loading shows a shimmer and no claim; a failed read says so', async () => {
    let resolve!: (v: unknown) => void
    trendMock.mockReturnValue(new Promise((r) => (resolve = r)) as never)
    const w = mount(NewFindingsStrip, { props, global: { stubs } })
    expect(w.find('[aria-label="Loading the new findings"]').exists()).toBe(true)
    expect(w.text()).not.toContain('No new findings')
    resolve({ data: null, response: { ok: false, status: 500 } })
    await flushPromises()
    expect(w.text()).toContain('JAVV cannot show the new findings. Check the backend connection.')
  })

  it('a filter that a past time refuses gets its own text, not the connection text', async () => {
    trendMock.mockResolvedValue({ data: null, response: { ok: false, status: 422 } } as never)
    const w = mount(NewFindingsStrip, {
      props: { ...props, t: '2026-09-20T23:59:59.999Z', filters: { kev: true } },
      global: { stubs },
    })
    await flushPromises()
    expect(w.text()).toContain('JAVV cannot count the new findings with these filters at a past time.')
    expect(w.text()).not.toContain('Check the backend connection')
  })

  it('an OK reply whose body could not be read is a failed read, not a throw (issue 749)', async () => {
    trendMock.mockResolvedValue(okWithoutBody())
    const w = mount(NewFindingsStrip, { props, global: { stubs } })
    await flushPromises()
    expect(w.text()).toContain('JAVV cannot show the new findings')
  })

  it('an older answer that lands last does not replace the newer one', async () => {
    let first!: (v: unknown) => void
    trendMock
      .mockReturnValueOnce(new Promise((r) => (first = r)) as never)
      .mockResolvedValueOnce(ok({ series: { high: [{ date: day(21), count: 7 }] } }))
    const w = mount(NewFindingsStrip, { props, global: { stubs } })
    await w.setProps({ filters: { scanner: 'grype' } })
    await flushPromises()
    first(ok({ series: { low: [{ date: day(21), count: 1 }] } }))
    await flushPromises()
    expect(w.text()).toContain('7 in this range')
  })

  it('a note of the screen follows the line of the strip', async () => {
    trendMock.mockResolvedValue(ok({ series: {} }))
    const w = mount(NewFindingsStrip, { props: { ...props, note: 'Only these filters apply.' }, global: { stubs } })
    await flushPromises()
    expect(w.find('.il-sub').text()).toBe('The findings first seen in each day, by severity. Only these filters apply.')
  })

  it('a click on a bar rewinds the app to the end of that bucket', async () => {
    vi.useFakeTimers({ now: new Date('2026-09-27T12:00:00Z'), toFake: ['Date'] })
    trendMock.mockResolvedValue(ok({ series: { high: [{ date: '2026-09-25T00:00:00.000Z', count: 2 }] } }))
    const w = mount(NewFindingsStrip, { props: { ...props, windowDays: 3 }, global: { stubs } })
    await flushPromises()
    const option = w.findComponent(EChart).props('option') as EChartsOption
    // the axis is the range 24 to 27 Sep: the bar of 25 Sep is the second bucket
    expect((option.series as BarSeriesOption[])[0]!.data).toEqual([0, 2, 0, 0])
    const timeTravel = useTimeTravelStore()
    w.findComponent(EChart).vm.$emit('point-click', { dataIndex: 1 })
    expect(timeTravel.t).toBe('2026-09-25T23:59:59.999Z')
  })
})

describe('useStripNow: one clock for the strips of a band', () => {
  afterEach(() => vi.useRealTimers())

  it('gives the same time to each strip, and moves with the clock each minute', () => {
    vi.useFakeTimers({ now: NOW, toFake: ['Date', 'setInterval', 'clearInterval'] })
    const scope = effectScope()
    const [a, b] = scope.run(() => [useStripNow(), useStripNow()])!
    expect(a.value).toBe(NOW)
    expect(b.value).toBe(a.value)
    vi.advanceTimersByTime(45 * 60_000)
    expect(a.value).toBe(NOW + 45 * 60_000)
    expect(b.value).toBe(a.value)
    scope.stop()
  })
})

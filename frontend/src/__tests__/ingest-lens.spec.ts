import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { BarSeriesOption } from 'echarts'

import { scannerFreshnessApiV1ScannersFreshnessGet, scansTrendApiV1TrendsScansGet } from '@/api/generated'
import {
  bucketEndT,
  buildIngestLensOption,
  ingestInterval,
  ingestLensDates,
} from '@/charts/buildIngestLensOption'
import type { ScanActivityData } from '@/charts/buildScanActivityOption'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { CHART_SCANNER } from '@/styles/tokens'

import { okWithoutBody } from './helpers/okWithoutBody'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    scansTrendApiV1TrendsScansGet: vi.fn<() => Promise<unknown>>(),
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
  }),
)

const pts = (scans: number[]) =>
  scans.map((n, i) => ({ date: `2026-07-0${i + 1}T00:00:00.000Z`, scans: n }))

describe('buildIngestLensOption (compact scan-activity variant)', () => {
  const data: ScanActivityData = { trivy: pts([2, 0, 1]), grype: pts([1, 1, 0]) }

  it('keeps one bar series per scanner — never merged — with the pinned colors', () => {
    const series = buildIngestLensOption(data).series as BarSeriesOption[]
    expect(series.map((s) => s.name)).toEqual(['trivy', 'grype'])
    expect(series[0]!.data).toEqual([2, 0, 1])
    expect((series[0]!.itemStyle as { color: string }).color).toBe(CHART_SCANNER.trivy)
    expect((series[1]!.itemStyle as { color: string }).color).toBe(CHART_SCANNER.grype)
  })

  it('squeezes the frame for the strip and pins whole-run y ticks', () => {
    const option = buildIngestLensOption(data)
    expect((option.grid as { top: number }).top).toBeLessThan(12)
    expect((option.yAxis as { minInterval: number }).minInterval).toBe(1)
  })

  it('empty series → no bars (the component renders the copy instead)', () => {
    expect((buildIngestLensOption({}).series as BarSeriesOption[]).length).toBe(0)
  })
})

describe('click-to-rewind mapping (D28: a day bucket → the whole-app T)', () => {
  it('dataIndex maps through the same date axis the bars use', () => {
    expect(ingestLensDates({ trivy: pts([2, 0, 1]) })).toEqual([
      '2026-07-01T00:00:00.000Z',
      '2026-07-02T00:00:00.000Z',
      '2026-07-03T00:00:00.000Z',
    ])
    // trivy absent → grype rows carry the axis
    expect(ingestLensDates({ grype: pts([1]) })).toEqual(['2026-07-01T00:00:00.000Z'])
  })

  it('a finished day rewinds to its END; a day still in progress is "now" (null)', () => {
    const nowMs = Date.parse('2026-07-10T12:00:00Z')
    expect(bucketEndT('2026-07-08T00:00:00.000Z', nowMs)).toBe('2026-07-08T23:59:59.999Z')
    expect(bucketEndT('2026-07-10T00:00:00.000Z', nowMs)).toBeNull()
  })

  it('hourly buckets rewind to the hour end (the 4-hour-cadence lens, audit 343)', () => {
    const nowMs = Date.parse('2026-07-10T12:30:00Z')
    expect(bucketEndT('2026-07-10T08:00:00.000Z', nowMs, 'hour')).toBe('2026-07-10T08:59:59.999Z')
    expect(bucketEndT('2026-07-10T12:00:00.000Z', nowMs, 'hour')).toBeNull()
  })
})

describe('ingestInterval (short live ranges bucket hourly)', () => {
  it('≤2 days at T=now → hour; longer or past T → day', () => {
    expect(ingestInterval(1, null)).toBe('hour')
    expect(ingestInterval(0.02, null)).toBe('hour')
    expect(ingestInterval(2, null)).toBe('hour')
    expect(ingestInterval(30, null)).toBe('day')
    expect(ingestInterval(1, '2026-07-08T00:00:00Z')).toBe('day') // the reader is daily-only
  })

  it('hourly option relabels the axis in HH:mm', () => {
    const series = { trivy: [{ date: '2026-07-10T08:00:00.000Z', scans: 2 }] }
    const opt = buildIngestLensOption(series, 'hour')
    expect((opt.xAxis as { data: string[] }).data.every((l) => /^\d{2}:\d{2}$/.test(l))).toBe(true)
  })
})

describe('IngestLens head (issue 341: the guide popover, plain copy)', () => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
  })
  const ok = <T,>(data: T) => ({ data, response: { ok: true, status: 200 } })

  async function mountLens(series: ScanActivityData) {
    vi.mocked(scansTrendApiV1TrendsScansGet).mockResolvedValue(ok({ series }) as never)
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(
      ok({
        scanners: [{ scanner: 'trivy', last_ingest_at: '2026-10-01T08:30:00Z', silent_for_seconds: 600 }],
      }) as never,
    )
    const w = mount(IngestLens, {
      props: { clusterId: 'c-1' },
      global: { plugins: [router], stubs: { EChart: true } },
    })
    await flushPromises()
    return w
  }

  beforeEach(() => setActivePinia(createPinia()))

  it('puts the guide popover beside the explanation, outside the part that truncates', async () => {
    const w = await mountLens({ trivy: pts([1]) })
    const help = w.find('.il-head > .il-help')
    expect(help.exists()).toBe(true)
    expect(w.find('.il-sub .il-help').exists()).toBe(false)
    await help.find('button').trigger('click')
    expect(help.find('a.gl-pop-link').attributes('href')).toBe('/guide#time-range')
  })

  it('a past sub-day range notes its daily bars without an em dash', async () => {
    const tt = useTimeTravelStore()
    tt.rewindTo('2026-09-30T12:00:00.000Z')
    tt.setWindow(0.25, 'Last 6 hours')
    const w = await mountLens({ trivy: pts([1]) })
    const sub = w.find('.il-sub').text()
    expect(sub).toContain('daily bars: covers the last 1 day')
    expect(sub).not.toContain('—')
  })

  it('a refused freshness read drops the old "last ingest" time for "-" (issue 833, F5)', async () => {
    const w = await mountLens({ trivy: pts([1]) })
    expect(w.find('.il-last').text()).toMatch(/^last ingest trivy/)
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue({
      error: {},
      response: { ok: false, status: 503 },
    } as never)
    useTimeTravelStore().setWindow(7, 'Last 7 days')
    await flushPromises()
    expect(w.find('.il-last').text()).toBe('last ingest -')
  })

  it('a quiet range at now says when the table was last updated, without an em dash', async () => {
    const w = await mountLens({})
    const empty = w.find('.il-empty').text()
    expect(empty).toMatch(/^No scans committed in this range: the table shows the state last updated/)
    expect(empty).not.toContain('—')
  })
})

// issue 749: the Overview threw "reading 'series'" from this read during the e2e suite
describe('IngestLens read', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('an OK reply whose body could not be read is a failed read, not a throw', async () => {
    const thrown: string[] = []
    vi.mocked(scansTrendApiV1TrendsScansGet).mockResolvedValue(okWithoutBody())
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(okWithoutBody())
    const w = mount(IngestLens, {
      props: { clusterId: 'c-1' },
      global: {
        plugins: [createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })],
        stubs: { EChart: true },
        config: { errorHandler: (err) => void thrown.push((err as Error).message) },
      },
    })
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.find('.il-empty').text()).toBe('Ingest activity unavailable.')
  })
})

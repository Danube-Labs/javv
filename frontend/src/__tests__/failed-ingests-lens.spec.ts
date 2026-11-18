import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import FailedIngestsLens from '@/components/dashboards/FailedIngestsLens.vue'
import EChart from '@/components/charts/EChart.vue'
import { useBucketRewind } from '@/composables/useBucketRewind'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { failuresAsLensSeries, totalRefused } from '@/system/ingestFailures'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    ingestFailuresTrendApiV1TrendsIngestFailuresGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { ingestFailuresTrendApiV1TrendsIngestFailuresGet } from '@/api/generated'

import { okWithoutBody } from './helpers/okWithoutBody'

const trendMock = vi.mocked(ingestFailuresTrendApiV1TrendsIngestFailuresGet)
const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
const pts = (counts: number[]) =>
  counts.map((count, i) => ({ date: `2026-09-2${i}T00:00:00.000Z`, count }))

describe('failuresAsLensSeries / totalRefused (pure)', () => {
  it('keeps one series per scanner, the count as the bar value', () => {
    expect(failuresAsLensSeries({ trivy: pts([0, 3]), grype: pts([2, 0]) })).toEqual({
      trivy: [
        { date: '2026-09-20T00:00:00.000Z', scans: 0 },
        { date: '2026-09-21T00:00:00.000Z', scans: 3 },
      ],
      grype: [
        { date: '2026-09-20T00:00:00.000Z', scans: 2 },
        { date: '2026-09-21T00:00:00.000Z', scans: 0 },
      ],
    })
    expect(failuresAsLensSeries({})).toEqual({})
  })

  it('totals every scanner and bucket, zero for an empty series', () => {
    expect(totalRefused({ trivy: pts([0, 3]), grype: pts([2, 0]) })).toBe(5)
    expect(totalRefused({})).toBe(0)
  })
})

describe('useBucketRewind (a bar click → the whole-app T)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('a finished bucket rewinds to its end; the bucket still running is now', () => {
    vi.useFakeTimers({ now: new Date('2026-09-27T12:00:00Z') })
    const timeTravel = useTimeTravelStore()
    const rewind = useBucketRewind()
    rewind('2026-09-25T00:00:00.000Z', 'day')
    expect(timeTravel.t).toBe('2026-09-25T23:59:59.999Z')
    expect(timeTravel.windowDays).toBe(30) // the range length stays; only its end moves
    rewind('2026-09-27T00:00:00.000Z', 'day')
    expect(timeTravel.t).toBeNull()
    rewind(undefined, 'day') // a click off the axis changes nothing
    expect(timeTravel.t).toBeNull()
    vi.useRealTimers()
  })
})

const props = { clusterId: 'c-k3d-0001', t: null, windowDays: 30 }
// the chart itself needs a real layout engine; the lens's job is the option and the click
const stubs = { EChart: true }

describe('FailedIngestsLens (self-contained lens)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('asks for the Scan ingest window and bucket size, and draws a bar per scanner', async () => {
    trendMock.mockResolvedValue(ok({ series: { trivy: pts([0, 3]), grype: pts([2, 0]) } }))
    const w = mount(FailedIngestsLens, { props, global: { stubs } })
    await flushPromises()
    expect(trendMock.mock.calls[0]![0]).toMatchObject({
      query: { cluster_id: 'c-k3d-0001', days: 30, interval: 'day' },
    })
    const option = w.findComponent(EChart).props('option') as { series: { name: string }[] }
    expect(option.series.map((s) => s.name)).toEqual(['trivy', 'grype'])
  })

  it('a short live range buckets hourly and a rewound one rides as_of, like Scan ingest', async () => {
    trendMock.mockResolvedValue(ok({ series: {} }))
    const w = mount(FailedIngestsLens, { props: { ...props, windowDays: 1 }, global: { stubs } })
    await flushPromises()
    expect(trendMock.mock.calls[0]![0]).toMatchObject({ query: { days: 1, interval: 'hour' } })
    await w.setProps({ t: '2026-09-20T23:59:59.999Z' })
    await flushPromises()
    expect(trendMock.mock.calls[1]![0]).toMatchObject({
      query: { days: 1, interval: 'day', as_of: '2026-09-20T23:59:59.999Z' },
    })
  })

  it('a range with no refusals is quiet copy, never an empty chart', async () => {
    trendMock.mockResolvedValue(ok({ series: { trivy: pts([0, 0]) } }))
    const w = mount(FailedIngestsLens, { props, global: { stubs } })
    await flushPromises()
    expect(w.findComponent(EChart).exists()).toBe(false)
    expect(w.text()).toContain('No refused scans in this range')
  })

  it('shows a loading shimmer before the answer and a plain error when the read fails', async () => {
    let resolve!: (v: unknown) => void
    trendMock.mockReturnValue(new Promise((r) => (resolve = r)) as never)
    const w = mount(FailedIngestsLens, { props, global: { stubs } })
    expect(w.find('[aria-label="Loading the refused scans"]').exists()).toBe(true)
    expect(w.text()).not.toContain('No refused scans') // no claim before evidence
    resolve({ data: null, response: { ok: false, status: 500 } })
    await flushPromises()
    expect(w.text()).toContain('JAVV cannot show the refused scans')
  })

  it('an OK reply whose body could not be read is a failed read, not a throw (issue 749)', async () => {
    const thrown: string[] = []
    trendMock.mockResolvedValue(okWithoutBody())
    const w = mount(FailedIngestsLens, {
      props,
      global: { stubs, config: { errorHandler: (err) => void thrown.push((err as Error).message) } },
    })
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.text()).toContain('JAVV cannot show the refused scans')
  })

  it('clicking a day rewinds the whole app to the end of that day', async () => {
    vi.useFakeTimers({ now: new Date('2026-09-27T12:00:00Z'), toFake: ['Date'] })
    trendMock.mockResolvedValue(ok({ series: { trivy: pts([0, 3]) } }))
    const w = mount(FailedIngestsLens, { props, global: { stubs } })
    await flushPromises()
    w.findComponent(EChart).vm.$emit('point-click', { dataIndex: 1 })
    expect(useTimeTravelStore().t).toBe('2026-09-21T23:59:59.999Z')
    vi.useRealTimers()
  })
})

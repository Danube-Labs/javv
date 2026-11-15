/**
 * A click on a bar of the Handled findings strip or the Audit activity strip sets the time of the
 * whole app to the end of that bucket, as the Scan ingest strip does (issue 1197). The bucket
 * still in progress means "now", and a click off the axis changes nothing.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import EChart from '@/components/charts/EChart.vue'
import ContributorsLens from '@/components/contributors/ContributorsLens.vue'
import AuditLens from '@/components/dashboards/AuditLens.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { lastDataAt } from '@/system/freshness'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    contributorsApiV1ContributorsGet: vi.fn<() => Promise<unknown>>(),
    auditFacetsApiV1AuditFacetsGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { auditFacetsApiV1AuditFacetsGet, contributorsApiV1ContributorsGet } from '@/api/generated'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
const days = [
  { date: '2026-09-25T00:00:00.000Z', count: 2 },
  { date: '2026-09-26T00:00:00.000Z', count: 1 },
  { date: '2026-09-27T00:00:00.000Z', count: 4 },
]
const hours = [
  { date: '2026-09-27T09:00:00.000Z', count: 3 },
  { date: '2026-09-27T12:00:00.000Z', count: 1 },
]
const stubs = { EChart: true }

function click(w: ReturnType<typeof mount>, dataIndex: number) {
  w.findComponent(EChart).vm.$emit('point-click', { dataIndex })
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.useFakeTimers({ now: new Date('2026-09-27T12:30:00Z'), toFake: ['Date'] })
})
afterEach(() => vi.useRealTimers())

describe('Handled findings strip: a click on a day', () => {
  it('fed by its screen: a finished day sets its end, today sets now, off the axis does nothing', async () => {
    const tt = useTimeTravelStore()
    const w = mount(ContributorsLens, { props: { series: days, settled: true, failed: false }, global: { stubs } })
    click(w, 0)
    expect(tt.t).toBe('2026-09-25T23:59:59.999Z')
    expect(tt.windowDays).toBe(30) // the range keeps its length, only its end moves
    expect(tt.windowLabel).toBe(`→ ${lastDataAt('2026-09-25T23:59:59.999Z')}`)
    click(w, 2)
    expect(tt.t).toBeNull()
    tt.rewindTo('2026-09-20T00:00:00.000Z')
    click(w, 9)
    expect(tt.t).toBe('2026-09-20T00:00:00.000Z')
  })

  it('with its own read, as on a dashboard', async () => {
    vi.mocked(contributorsApiV1ContributorsGet).mockResolvedValue(ok({ handled_over_time: days }))
    const tt = useTimeTravelStore()
    const w = mount(ContributorsLens, { props: { query: { cluster_id: 'c-1', days: 30 } }, global: { stubs } })
    await flushPromises()
    click(w, 1)
    expect(tt.t).toBe('2026-09-26T23:59:59.999Z')
  })
})

describe('Audit activity strip: a click on a bucket', () => {
  it('a day bucket sets its end, today sets now, off the axis does nothing', async () => {
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValue(ok({ activity: days }))
    const tt = useTimeTravelStore()
    const w = mount(AuditLens, { props: { query: { cluster_id: 'c-1' } }, global: { stubs } })
    await flushPromises()
    click(w, 1)
    expect(tt.t).toBe('2026-09-26T23:59:59.999Z')
    expect(tt.windowLabel).toBe(`→ ${lastDataAt('2026-09-26T23:59:59.999Z')}`)
    click(w, 2)
    expect(tt.t).toBeNull()
    click(w, 9)
    expect(tt.t).toBeNull()
  })

  it('an hour bucket of a short range sets the end of that hour', async () => {
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValue(ok({ activity: hours }))
    const tt = useTimeTravelStore()
    tt.setWindow(1, 'Last 24 hours')
    const w = mount(AuditLens, { props: { query: { cluster_id: 'c-1' } }, global: { stubs } })
    await flushPromises()
    expect(vi.mocked(auditFacetsApiV1AuditFacetsGet).mock.calls[0]![0]).toMatchObject({
      query: { interval: 'hour' },
    })
    // the hour in progress first: once T is in the past, the strip buckets by day
    click(w, 1)
    expect(tt.t).toBeNull()
    click(w, 0)
    expect(tt.t).toBe('2026-09-27T09:59:59.999Z')
    expect(tt.windowDays).toBe(1)
  })
})

/**
 * Vulnerabilities over time as a dashboard panel (issue 1176): the Overview chart, one set of
 * lines per scanner, never merged. The panel reads `/trends/findings` itself, and the scanner
 * switch picks lines from the answer, because the route gives both scanners at a past T.
 */
import { flushPromises, mount } from '@vue/test-utils'
import type { LineSeriesOption } from 'echarts'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  buildFindingsTrendOption,
  trendForScanner,
  type FindingsTrendData,
} from '@/charts/buildFindingsTrendOption'
import EChart from '@/components/charts/EChart.vue'
import FindingsTrendLens from '@/components/dashboards/FindingsTrendLens.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    findingsTrendApiV1TrendsFindingsGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { findingsTrendApiV1TrendsFindingsGet } from '@/api/generated'

import { okWithoutBody } from './helpers/okWithoutBody'

const trendMock = vi.mocked(findingsTrendApiV1TrendsFindingsGet)
const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
const pts = (counts: number[]) =>
  counts.map((count, i) => ({ date: `2026-10-2${i}T00:00:00.000Z`, count }))
const BOTH: FindingsTrendData = {
  new: { trivy: pts([4, 1]), grype: pts([2, 3]) },
  resolved: { trivy: pts([0, 2]), grype: pts([1, 0]) },
}
const names = (option: unknown) =>
  ((option as { series: LineSeriesOption[] }).series ?? []).map((s) => s.name)

describe('trendForScanner (pure)', () => {
  it('keeps both scanners for All scanners', () => {
    expect(trendForScanner(BOTH, 'all')).toBe(BOTH)
  })

  it.each(['trivy', 'grype'] as const)('keeps only the new and resolved lines of %s', (scanner) => {
    const other = scanner === 'trivy' ? 'grype' : 'trivy'
    const picked = trendForScanner(BOTH, scanner)
    expect(picked.new[scanner]).toEqual(BOTH.new[scanner])
    expect(picked.resolved[scanner]).toEqual(BOTH.resolved[scanner])
    expect(picked.new[other]).toBeUndefined()
    expect(picked.resolved[other]).toBeUndefined()
    expect(names(buildFindingsTrendOption(picked))).toEqual([
      `new · ${scanner}`,
      `resolved (scan-observed) · ${scanner}`,
    ])
  })

  it('a scanner with no lines in the answer gives no lines, not the other scanner', () => {
    const trivyOnly: FindingsTrendData = { new: { trivy: pts([1]) }, resolved: {} }
    expect(names(buildFindingsTrendOption(trendForScanner(trivyOnly, 'grype')))).toEqual([])
  })
})

const props = { clusterId: 'c-k3d-0001', t: null, windowDays: 30, scanner: 'all' as const }
// the chart itself needs a real layout engine; the panel's job is the read and the option
const stubs = { EChart: true }

describe('FindingsTrendLens (self-contained panel)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('reads the range of the dashboard at now, with no as_of and no scanner', async () => {
    trendMock.mockResolvedValue(ok(BOTH))
    const w = mount(FindingsTrendLens, { props, global: { stubs } })
    await flushPromises()
    expect(trendMock).toHaveBeenCalledTimes(1)
    expect(trendMock.mock.calls[0]![0]).toEqual({
      client: {},
      query: { cluster_id: 'c-k3d-0001', days: 30 },
    })
    expect(names(w.findComponent(EChart).props('option'))).toEqual([
      'new · trivy',
      'resolved (scan-observed) · trivy',
      'new · grype',
      'resolved (scan-observed) · grype',
    ])
  })

  it('at a past T sends as_of, and the switch still shows one scanner from an answer with both', async () => {
    trendMock.mockResolvedValue(ok(BOTH)) // the past-T reader ignores `scanner`: both come back
    const w = mount(FindingsTrendLens, {
      props: { ...props, t: '2026-10-21T23:59:59.999Z', scanner: 'grype' },
      global: { stubs },
    })
    await flushPromises()
    expect(trendMock.mock.calls[0]![0]).toMatchObject({
      query: { cluster_id: 'c-k3d-0001', days: 30, as_of: '2026-10-21T23:59:59.999Z' },
    })
    expect(names(w.findComponent(EChart).props('option'))).toEqual([
      'new · grype',
      'resolved (scan-observed) · grype',
    ])
  })

  it('a change of the scanner switch draws again and starts no read', async () => {
    trendMock.mockResolvedValue(ok(BOTH))
    const w = mount(FindingsTrendLens, { props, global: { stubs } })
    await flushPromises()
    await w.setProps({ scanner: 'trivy' })
    await flushPromises()
    expect(trendMock).toHaveBeenCalledTimes(1)
    expect(names(w.findComponent(EChart).props('option'))).toEqual([
      'new · trivy',
      'resolved (scan-observed) · trivy',
    ])
  })

  it('an older answer that comes last does not replace the answer of the newer read', async () => {
    let old!: (v: unknown) => void
    trendMock.mockReturnValueOnce(new Promise((r) => (old = r)) as never)
    trendMock.mockResolvedValueOnce(ok({ new: { grype: pts([7]) }, resolved: {} }))
    const w = mount(FindingsTrendLens, { props, global: { stubs } })
    await w.setProps({ clusterId: 'c-k3d-0002' })
    await flushPromises()
    old(ok(BOTH))
    await flushPromises()
    expect(names(w.findComponent(EChart).props('option'))).toEqual(['new · grype'])
  })

  it('a range of less than 1 day reads 1 day and says so', async () => {
    trendMock.mockResolvedValue(ok(BOTH))
    const w = mount(FindingsTrendLens, { props: { ...props, windowDays: 0.25 }, global: { stubs } })
    await flushPromises()
    expect(trendMock.mock.calls[0]![0]).toMatchObject({ query: { days: 1 } })
    expect(w.text()).toContain('Trend at daily resolution: chart covers the last 1 day.')
  })

  it('a range with no lines is quiet copy, never an empty chart', async () => {
    trendMock.mockResolvedValue(ok({ new: {}, resolved: {} }))
    const w = mount(FindingsTrendLens, { props, global: { stubs } })
    await flushPromises()
    expect(w.findComponent(EChart).exists()).toBe(false)
    expect(w.text()).toContain('No new or resolved findings in this range.')
  })

  it('shows a loading shimmer before the answer and a plain error when the read fails', async () => {
    let resolve!: (v: unknown) => void
    trendMock.mockReturnValue(new Promise((r) => (resolve = r)) as never)
    const w = mount(FindingsTrendLens, { props, global: { stubs } })
    expect(w.find('[aria-label="Loading vulnerabilities over time"]').exists()).toBe(true)
    expect(w.text()).not.toContain('No new or resolved findings') // no claim before evidence
    resolve({ data: null, response: { ok: false, status: 500 } })
    await flushPromises()
    expect(w.text()).toContain('Vulnerability trend unavailable.')
  })

  it('an OK reply whose body could not be read is a failed read, not a throw (issue 749)', async () => {
    const thrown: string[] = []
    trendMock.mockResolvedValue(okWithoutBody())
    const w = mount(FindingsTrendLens, {
      props,
      global: { stubs, config: { errorHandler: (err) => void thrown.push((err as Error).message) } },
    })
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.text()).toContain('Vulnerability trend unavailable.')
  })
})

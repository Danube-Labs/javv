import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import IngestFailuresTable from '@/components/scanners/IngestFailuresTable.vue'
import { buildIngestFailuresQuery, type IngestFailureRow } from '@/system/ingestFailures'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    scannerIngestFailuresApiV1ScannersIngestFailuresGet: vi.fn<() => Promise<unknown>>(),
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
    scannerProvenanceApiV1ScannersProvenanceGet: vi.fn<() => Promise<unknown>>(),
    scansTrendApiV1TrendsScansGet: vi.fn<() => Promise<unknown>>(),
    ingestFailuresTrendApiV1TrendsIngestFailuresGet: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import {
  ingestFailuresTrendApiV1TrendsIngestFailuresGet,
  scannerFreshnessApiV1ScannersFreshnessGet,
  scannerIngestFailuresApiV1ScannersIngestFailuresGet,
  scannerProvenanceApiV1ScannersProvenanceGet,
  scansTrendApiV1TrendsScansGet,
} from '@/api/generated'

const failuresMock = vi.mocked(scannerIngestFailuresApiV1ScannersIngestFailuresGet)
const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never

const row = (i: number, over: Partial<IngestFailureRow> = {}): IngestFailureRow => ({
  '@timestamp': `2026-09-26T1${i}:00:00+00:00`,
  failure_id: `f${i}`,
  scanner: 'grype',
  stage: 'validate',
  reason: 'invalid_envelope',
  status: 422,
  error: 'envelope rejected: 1 error(s); first: findings.3.severity: missing',
  image_ref: `registry.example.com/team/api:v${i}`,
  ...over,
})
const page = (rows: IngestFailureRow[], total: number, next: string | null) =>
  ok({ data: rows, total: { value: total, relation: 'eq' }, next_cursor: next })

const props = { clusterId: 'c-k3d-0001', scanner: 'grype' as const, t: null, windowDays: 30 }
const mountTable = (over: Partial<typeof props> = {}) =>
  mount(IngestFailuresTable, { props: { ...props, ...over } })

describe('buildIngestFailuresQuery (pure: the params the panel emits)', () => {
  it('is the trend window plus one scanner, with the cursor only when paging', () => {
    const q = buildIngestFailuresQuery({ ...props, size: 10, cursor: null })
    expect(q).toEqual({ cluster_id: 'c-k3d-0001', days: 30, scanner: 'grype', size: 10 })
  })

  it('rides as_of only at a rewound T, and carries the cursor it is given', () => {
    const q = buildIngestFailuresQuery({ ...props, t: '2026-09-20T00:00:00Z', size: 25, cursor: 'c1' })
    expect(q).toMatchObject({ as_of: '2026-09-20T00:00:00Z', cursor: 'c1', size: 25 })
  })

  it('a range of 2 days or less at now sends its length, as the strip above it (issue 1291, Q1 A)', () => {
    const q = buildIngestFailuresQuery({ ...props, windowDays: 0.25, size: 10, cursor: null })
    expect(q.window_seconds).toBe(21_600)
    expect(q.days).toBeUndefined()
  })

  it('a longer range, or a past T, sends whole days, like every trend', () => {
    expect(buildIngestFailuresQuery({ ...props, windowDays: 2.5, size: 10, cursor: null }).days).toBe(3)
    const past = buildIngestFailuresQuery({ ...props, windowDays: 0.25, t: '2026-09-20T12:00:00Z', size: 10, cursor: null })
    expect(past.days).toBe(1)
    expect(past.window_seconds).toBeUndefined()
  })
})

describe('IngestFailuresTable (self-contained panel)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('claims nothing before the first answer lands', async () => {
    failuresMock.mockReturnValue(new Promise(() => {}) as never)
    const w = mountTable()
    await flushPromises()
    expect(w.find('[aria-busy="true"]').exists()).toBe(true)
    expect(w.text()).not.toContain('No refused scans')
  })

  it('renders one row per failure, newest first as served, with the full text on hover', async () => {
    failuresMock.mockResolvedValue(page([row(2), row(1, { image_ref: null, stage: 'decode' })], 2, null))
    const w = mountTable()
    await flushPromises()
    const trs = w.findAll('tbody tr')
    expect(trs).toHaveLength(2)
    expect(trs[0]!.text()).toContain('registry.example.com/team/api:v2')
    expect(trs[0]!.text()).toContain('422')
    expect(trs[0]!.find('[title^="422 ·"]').attributes('title')).toContain('findings.3.severity')
    // the scan had no image that JAVV could read: nothing to show, and no invented one
    expect(trs[1]!.find('.muted-dash').text()).toBe('-')
    expect(trs[1]!.text()).toContain('decode')
    expect(w.text()).not.toMatch(/retry/i) // read-only by ruling: no retry column or action
  })

  it('an empty answer says so honestly', async () => {
    failuresMock.mockResolvedValue(page([], 0, null))
    const w = mountTable()
    await flushPromises()
    expect(w.text()).toContain('No refused scans in this range.')
    expect(w.find('table').exists()).toBe(false)
  })

  it('a failed read is an error state, never an empty one', async () => {
    failuresMock.mockResolvedValue({ data: undefined, response: { ok: false, status: 503 } } as never)
    const w = mountTable()
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toBe('JAVV cannot show the refused scans. Check the backend connection.')
    expect(w.text()).not.toContain('No refused scans')
  })

  it('pages on the server cursor and walks back on the remembered one', async () => {
    failuresMock
      .mockResolvedValueOnce(page([row(9)], 3, 'c1'))
      .mockResolvedValueOnce(page([row(8)], 3, null))
      .mockResolvedValueOnce(page([row(9)], 3, 'c1'))
    const w = mountTable()
    await flushPromises()
    const call = (n: number) => (failuresMock.mock.calls[n]![0] as { query: Record<string, unknown> }).query
    expect(call(0).cursor).toBeUndefined()

    await w.findAll('.pager-btn')[1]!.trigger('click') // Next
    await flushPromises()
    expect(call(1).cursor).toBe('c1')
    expect(w.text()).toContain('api:v8')

    await w.findAll('.pager-btn')[0]!.trigger('click') // Prev
    await flushPromises()
    expect(call(2).cursor).toBeUndefined()
  })

  it('refetches from page 0 for its own inputs — another scanner, cluster or T', async () => {
    failuresMock.mockResolvedValue(page([row(1)], 1, null))
    const w = mountTable()
    await flushPromises()
    await w.setProps({ scanner: 'trivy' })
    await flushPromises()
    await w.setProps({ t: '2026-09-20T00:00:00Z' })
    await flushPromises()
    const queries = failuresMock.mock.calls.map((c) => (c[0] as { query: Record<string, unknown> }).query)
    expect(queries.map((q) => q.scanner)).toEqual(['grype', 'trivy', 'trivy'])
    expect(queries[2]!.as_of).toBe('2026-09-20T00:00:00Z')
    expect(queries.every((q) => q.cursor === undefined)).toBe(true)
  })
})

describe('ScannerStatusView wiring', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('mounts one failures panel per scanner, each asking for its own scanner only', async () => {
    const { useClusterStore } = await import('@/stores/cluster')
    const { default: ScannerStatusView } = await import('@/views/ScannerStatusView.vue')
    useClusterStore().selectedId = 'c-k3d-0001'
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(
      ok({ scanners: [{ scanner: 'grype' }, { scanner: 'trivy' }] }),
    )
    vi.mocked(scannerProvenanceApiV1ScannersProvenanceGet).mockResolvedValue(ok({ scanners: [] }))
    vi.mocked(scansTrendApiV1TrendsScansGet).mockResolvedValue(ok({ series: {} }))
    vi.mocked(ingestFailuresTrendApiV1TrendsIngestFailuresGet).mockResolvedValue(ok({ series: {} }))
    failuresMock.mockResolvedValue(page([], 0, null))

    const w = mount(ScannerStatusView)
    await flushPromises()

    expect(w.findAllComponents(IngestFailuresTable)).toHaveLength(2)
    // the failed-ingests strip joins Scan ingest in the head band, for the same cluster
    const strip = w.find('.screen-head-band .lens-stack')
    expect(strip.findAll('section').map((s) => s.attributes('aria-label'))).toEqual([
      'Scan ingest activity',
      'Failed ingest activity',
    ])
    expect(vi.mocked(ingestFailuresTrendApiV1TrendsIngestFailuresGet).mock.calls[0]![0]).toMatchObject({
      query: { cluster_id: 'c-k3d-0001' },
    })
    const asked = failuresMock.mock.calls.map((c) => (c[0] as { query: { scanner: string } }).query.scanner)
    expect(asked.sort()).toEqual(['grype', 'trivy'])

    // one lane per scanner, each named and carrying its identity hook for the head colour
    const lanes = w.findAll('section.lane')
    expect(lanes.map((l) => l.attributes('data-scanner'))).toEqual(['grype', 'trivy'])
    expect(lanes.map((l) => l.find('.lane-head').text())).toEqual(['grype', 'trivy'])
    // the narrow-screen picker starts on the first lane; the other is the one CSS hides there
    expect(lanes.map((l) => l.classes('lane-off'))).toEqual([false, true])
    await w.findAll('.lane-pick button')[1]!.trigger('click')
    expect(w.findAll('section.lane').map((l) => l.classes('lane-off'))).toEqual([true, false])
  })
})

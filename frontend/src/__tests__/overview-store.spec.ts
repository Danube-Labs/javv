/**
 * The Overview store's load (issue 749): an OK reply whose body could not be read is a failed load.
 * The view starts `load` from a watcher without awaiting it, so a throw here is a rejection
 * nothing catches.
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    facetFindingsApiV1FindingsFacetsGet: vi.fn<() => Promise<unknown>>(),
    findingsTrendApiV1TrendsFindingsGet: vi.fn<() => Promise<unknown>>(),
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import {
  facetFindingsApiV1FindingsFacetsGet,
  findingsTrendApiV1TrendsFindingsGet,
  scannerFreshnessApiV1ScannersFreshnessGet,
} from '@/api/generated'
import { useOverviewStore } from '@/stores/overview'

import { okWithoutBody } from './helpers/okWithoutBody'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
const FACETS = { facets: { present: [{ key: 'true', count: 3, by_scanner: { trivy: 3 } }] } }
const TREND = { new: { trivy: [{ date: '2026-10-01T00:00:00.000Z', count: 3 }] }, resolved: {} }
const FRESH = { scanners: [{ last_ingest_at: '2026-10-01T08:00:00Z' }] }

describe('useOverviewStore().load', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(facetFindingsApiV1FindingsFacetsGet).mockResolvedValue(ok(FACETS))
    vi.mocked(findingsTrendApiV1TrendsFindingsGet).mockResolvedValue(ok(TREND))
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(ok(FRESH))
  })

  it('the trend of findings reads whole days, also for a short range (issue 1291)', async () => {
    const store = useOverviewStore()
    await store.load({ cluster_id: 'c-1' }, 1 / 24)
    await store.loadSeverityTrend('c-1', 1 / 24, null)
    const queries = vi.mocked(findingsTrendApiV1TrendsFindingsGet).mock.calls.map((c) => (c[0] as { query: object }).query)
    expect(queries).toEqual([
      { cluster_id: 'c-1', days: 1 },
      { cluster_id: 'c-1', days: 1, split: 'severity' },
    ])
  })

  it('keeps what the server returned', async () => {
    const store = useOverviewStore()
    await store.load({ cluster_id: 'c-1' }, 30)
    expect(store.failed).toBe(false)
    expect(store.facets).toEqual(FACETS.facets)
    expect(store.trend).toEqual(TREND)
    expect(store.lastIngestAt).toBe('2026-10-01T08:00:00Z')
  })

  it.each([
    ['facets', facetFindingsApiV1FindingsFacetsGet],
    ['trend', findingsTrendApiV1TrendsFindingsGet],
  ] as const)('an OK %s reply whose body could not be read fails the load', async (_name, call) => {
    vi.mocked(call).mockResolvedValue(okWithoutBody())
    const store = useOverviewStore()
    await expect(store.load({ cluster_id: 'c-1' }, 30)).resolves.toBeUndefined()
    expect(store.failed).toBe(true)
    expect(store.facets).toEqual({})
  })
})

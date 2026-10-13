import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import ImageDetailView from '@/views/ImageDetailView.vue'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    facetFindingsApiV1FindingsFacetsGet: vi.fn<() => Promise<unknown>>(),
    searchFindingsApiV1FindingsGet: vi.fn<() => Promise<unknown>>(),
    listRunningImagesApiV1ImagesGet: vi.fn<() => Promise<unknown>>(),
    imageTimelineApiV1ImagesTimelineGet: vi.fn<() => Promise<unknown>>(),
    // the ingest lens (audit 343) mounts inside the view and calls these two
    scansTrendApiV1TrendsScansGet: vi.fn<() => Promise<unknown>>(),
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import {
  facetFindingsApiV1FindingsFacetsGet,
  imageTimelineApiV1ImagesTimelineGet,
  listRunningImagesApiV1ImagesGet,
  scannerFreshnessApiV1ScannersFreshnessGet,
  scansTrendApiV1TrendsScansGet,
  searchFindingsApiV1FindingsGet,
} from '@/api/generated'

const facetsMock = vi.mocked(facetFindingsApiV1FindingsFacetsGet)
const searchMock = vi.mocked(searchFindingsApiV1FindingsGet)
const inventoryMock = vi.mocked(listRunningImagesApiV1ImagesGet)
const timelineMock = vi.mocked(imageTimelineApiV1ImagesTimelineGet)

const row = (key: string, scanner: string) =>
  ({
    finding_key: key,
    cve_id: 'CVE-1',
    scanner,
    severity: 'High',
    severity_canonical: 'high',
    state: 'open',
    package_name: 'curl',
    installed_version: '7.74.0',
    fixed_version: null,
    fixable: false,
    namespaces: ['ns'],
    epss: null,
    kev: false,
    disagree: false,
    image_repo: 'docker.io/library/nginx',
    tag: '1.21.6',
  }) as never

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/images/:digest', name: 'image-detail', component: ImageDetailView },
    { path: '/images', name: 'images', component: { template: '<div />' } },
    { path: '/findings/:cveId', name: 'finding', component: { template: '<div />' } },
  ],
})

describe('ImageDetailView (M9c slice 3)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useClusterStore().clusters = [{ cluster_id: 'c-1', cluster_name: 'c-1' }]
    useClusterStore().selectedId = 'c-1'
    inventoryMock.mockResolvedValue(
      ok({ inventory: { inventory_run_id: 'r1' }, images: [] }) as never,
    )
    timelineMock.mockResolvedValue(ok({ events: [] }) as never)
    vi.mocked(scansTrendApiV1TrendsScansGet).mockResolvedValue(ok({ series: {}, days: 30 }) as never)
    vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(
      ok({ scanners: [] }) as never,
    )
  })

  it('scanner lens SWAPS the per-scanner reads — rows replaced, never merged', async () => {
    facetsMock.mockResolvedValue(
      ok({ facets: { severity: [{ key: 'critical', count: 3 }], present: [{ key: 'true', count: 10 }] } }) as never,
    )
    searchMock.mockResolvedValue(
      ok({ data: [row('t-1', 'trivy')], total: { value: 1 }, next_cursor: null }) as never,
    )
    await router.push('/images/sha256:abc?repo=docker.io/library/nginx&tag=1.21.6')
    const w = mount(ImageDetailView, { global: { plugins: [router] } })
    await flushPromises()

    // every read is digest-scoped and single-scanner
    const firstQ = (searchMock.mock.calls[0]![0] as { query: Record<string, unknown> }).query
    expect(firstQ).toMatchObject({ cluster_id: 'c-1', image_digest: 'sha256:abc', scanner: 'trivy' })
    expect(w.findAll('tbody tr')).toHaveLength(1)

    searchMock.mockResolvedValue(
      ok({ data: [row('g-1', 'grype'), row('g-2', 'grype')], total: { value: 2 }, next_cursor: null }) as never,
    )
    const grypeBtn = w.findAll('button').find((b) => b.text() === 'grype')!
    await grypeBtn.trigger('click')
    await flushPromises()

    const lastQ = (searchMock.mock.calls.at(-1)![0] as { query: Record<string, unknown> }).query
    expect(lastQ).toMatchObject({ scanner: 'grype', image_digest: 'sha256:abc' })
    expect(w.findAll('tbody tr')).toHaveLength(2) // grype's rows REPLACE trivy's — no union
    expect(w.text()).toContain('nginx:1.21.6')
  })

  it('empty per-scanner result renders the explicit empty state, not an error', async () => {
    facetsMock.mockResolvedValue(ok({ facets: {} }) as never)
    searchMock.mockResolvedValue(ok({ data: [], total: { value: 0 }, next_cursor: null }) as never)
    await router.push('/images/sha256:clean?repo=r&tag=t')
    const w = mount(ImageDetailView, { global: { plugins: [router] } })
    await flushPromises()
    expect(w.text()).toContain('No findings from trivy')
  })

  // issue 833, F5: an empty timeline from a refused read read as "never scanned before this T"
  it.each([
    [ok({ events: [] }), true],
    [{ error: {}, response: { ok: false, status: 503 } }, false],
  ])('at a past T, a timeline answer %#: "not yet scanned" only when it truly answered', async (answer, notYet) => {
    useTimeTravelStore().rewindTo('2026-09-30T12:00:00.000Z')
    facetsMock.mockResolvedValue(ok({ facets: {} }) as never)
    searchMock.mockResolvedValue(ok({ data: [], total: { value: 0 }, next_cursor: null }) as never)
    timelineMock.mockResolvedValue(answer as never)
    await router.push('/images/sha256:past?repo=r&tag=t')
    const w = mount(ImageDetailView, { global: { plugins: [router] } })
    await flushPromises()
    // the second stat cell answers "what did the scanner find?"; the view's own card is titled
    expect(w.findAll('.tq-ans')[1]!.text() === 'not yet scanned').toBe(notYet)
    expect(w.findAll('h2').some((h) => h.text() === 'Not yet scanned then')).toBe(notYet)
    expect(w.find('.tl-card .load-error').exists()).toBe(!notYet)
  })
})

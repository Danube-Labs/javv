import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { historySummary } from '@/images/subTimeline'
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
    { path: '/findings', name: 'findings', component: { template: '<div />' } },
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
    // the Paths column needs the paths on every page: the cursor does not keep it (issue 1077)
    expect(firstQ.locations).toBe(true)
    expect(w.findAll('thead th').map((th) => th.text())).toContain('Paths')
    expect(w.findAll('tbody tr')).toHaveLength(1)

    searchMock.mockResolvedValue(
      ok({ data: [row('g-1', 'grype'), row('g-2', 'grype')], total: { value: 2 }, next_cursor: null }) as never,
    )
    const grypeBtn = w.findAll('button').find((b) => b.text() === 'grype')!
    await grypeBtn.trigger('click')
    await flushPromises()

    const lastQ = (searchMock.mock.calls.at(-1)![0] as { query: Record<string, unknown> }).query
    expect(lastQ).toMatchObject({ scanner: 'grype', image_digest: 'sha256:abc', locations: true })
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

  // issue 1140, R5 to R7 (operator ruling on built pictures, option B1)
  describe('the band of three columns', () => {
    const ev = (at: string, digest: string, scanner = 'trivy', order = 1) =>
      ({ scan_order: order, '@timestamp': at, scanner, image_digest: digest, total: 3 }) as never
    async function mountImage() {
      facetsMock.mockResolvedValue(ok({ facets: { present: [{ key: 'true', count: 1167 }] } }) as never)
      searchMock.mockResolvedValue(ok({ data: [], total: { value: 0 }, next_cursor: null }) as never)
      inventoryMock.mockResolvedValue(
        ok({
          inventory: { inventory_run_id: 'r1', completed_at: '2026-11-02T12:46:00Z' },
          images: [{ image_digest: 'sha256:abc', replicas: 1, namespaces: ['data'] }],
        }) as never,
      )
      timelineMock.mockResolvedValue(
        ok({ events: [ev('2026-10-06T12:00:00Z', 'sha256:abc', 'trivy', 1), ev('2026-11-02T12:35:00Z', 'sha256:abc', 'trivy', 2), ev('2026-11-02T12:40:00Z', 'sha256:abc', 'grype', 1)] }) as never,
      )
      await router.push('/images/sha256:abc?repo=docker.io/library/postgres&tag=13.4')
      const w = mount(ImageDetailView, { global: { plugins: [router] }, attachTo: document.body })
      await flushPromises()
      return w
    }

    it('shows Running now, Findings of the scanner and Build history, and the head lost its meta line', async () => {
      const w = await mountImage()
      const cells = w.findAll('.two-q .stat-cell')
      expect(cells.map((c) => c.find('.stat-label').text())).toEqual(['running now', 'findings of trivy', 'build history'])
      expect(cells[0]!.text()).toContain('yes · 1 replica')
      expect(cells[0]!.find('.stat-sub').text()).toContain('data · from the inventory of')
      expect(cells[1]!.text()).toContain('1,167 findings')
      expect(cells[2]!.find('.stat-num').text()).toBe('1 digest · 2 scans')
      expect(cells[2]!.find('.stat-sub').text()).toBe('trivy, 6 Oct to 2 Nov')
      expect(w.find('.img-meta').exists()).toBe(false)
      w.unmount()
    })

    it('Build history opens and closes the card, closed when the page opens', async () => {
      const w = await mountImage()
      const btn = w.findAll('.two-q button.stat-cell').find((b) => b.text().includes('build history'))!
      const card = w.get('#build-history')
      expect(btn.attributes('aria-expanded')).toBe('false')
      expect(btn.attributes('aria-controls')).toBe('build-history')
      expect(card.isVisible()).toBe(false)
      await btn.trigger('click')
      expect(btn.attributes('aria-expanded')).toBe('true')
      expect(card.isVisible()).toBe(true)
      await btn.trigger('click')
      expect(card.isVisible()).toBe(false)
      w.unmount()
    })

    it('Findings opens Findings on this digest and scanner', async () => {
      const w = await mountImage()
      await w.findAll('.two-q button')[0]!.trigger('click')
      await flushPromises()
      expect(router.currentRoute.value.path).toBe('/findings')
      expect(router.currentRoute.value.query).toEqual({ digest: 'sha256:abc', scanner: 'trivy' })
      w.unmount()
    })
  })
})

describe('historySummary', () => {
  const ev = (at: string, digest: string, scanner = 'trivy') =>
    ({ scan_order: 1, '@timestamp': at, scanner, image_digest: digest, total: 1 }) as never
  const events = [ev('2026-10-01T00:00:00Z', 'a'), ev('2026-10-05T00:00:00Z', 'b'), ev('2026-10-09T00:00:00Z', 'b'), ev('2026-10-02T00:00:00Z', 'a', 'grype')]

  it('counts one scanner\'s digests and scans, with the first and last date', () => {
    expect(historySummary(events, 'trivy', null)).toEqual({ digests: 2, scans: 3, firstAt: '2026-10-01T00:00:00Z', lastAt: '2026-10-09T00:00:00Z' })
  })

  it('stops at T, and gives nothing for a scanner with no scan', () => {
    expect(historySummary(events, 'trivy', '2026-10-06T00:00:00Z')).toEqual({ digests: 2, scans: 2, firstAt: '2026-10-01T00:00:00Z', lastAt: '2026-10-05T00:00:00Z' })
    expect(historySummary([], 'grype', null)).toEqual({ digests: 0, scans: 0, firstAt: null, lastAt: null })
  })
})

/**
 * The dashboard panel catalog (issue 440). Every panel in it must render on a page that gives it
 * nothing but a cluster and its settings (DESIGN.md §10): it sends its own request, and shows its
 * own loading, empty and error states. Here each panel mounts alone, with only that.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    topComponentsFindingsApiV1FindingsTopComponentsGet: vi.fn<() => Promise<unknown>>(),
    scansTrendApiV1TrendsScansGet: vi.fn<() => Promise<unknown>>(),
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
    ingestFailuresTrendApiV1TrendsIngestFailuresGet: vi.fn<() => Promise<unknown>>(),
    auditFacetsApiV1AuditFacetsGet: vi.fn<() => Promise<unknown>>(),
    facetFindingsApiV1FindingsFacetsGet: vi.fn<() => Promise<unknown>>(),
    listRunningImagesApiV1ImagesGet: vi.fn<() => Promise<unknown>>(),
    contributorsApiV1ContributorsGet: vi.fn<() => Promise<unknown>>(),
    findingsTrendApiV1TrendsFindingsGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import * as sdk from '@/api/generated'
import ContributorsLens from '@/components/contributors/ContributorsLens.vue'
import PanelFrame from '@/components/dashboards/PanelFrame.vue'
import OverviewNamespacesCard from '@/components/overview/OverviewNamespacesCard.vue'
import OverviewStatBands from '@/components/overview/OverviewStatBands.vue'
import PackageTypeCard from '@/components/overview/PackageTypeCard.vue'
import {
  PANELS,
  TABLE_ROWS,
  globalQuery,
  heightsOf,
  panelById,
  type CatalogPanel,
  type PanelContext,
} from '@/dashboards/catalog'
import { panelPropsCache, placePanels } from '@/dashboards/layout'
import { useClusterStore } from '@/stores/cluster'
import OverviewView from '@/views/OverviewView.vue'

const CLUSTER = 'c-k3d-0001'
const ctx = (over: Partial<PanelContext> = {}): PanelContext => ({
  clusterId: CLUSTER,
  t: null,
  windowDays: 30,
  scanner: 'all',
  height: 'short',
  ...over,
})
const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
const refused = () => ({ data: null, response: { ok: false, status: 500 } }) as never
/** a committed inventory; `inventory: null` is the other answer, that none is committed yet */
const INVENTORY = {
  inventory_run_id: 'run-1',
  inventory_order: 1,
  started_at: '2026-10-20T10:00:00.000Z',
  completed_at: '2026-10-20T10:05:00.000Z',
}

type SdkName = keyof typeof sdk
/** For each panel: the reads it sends, an empty answer for each, and the copy of each state. */
const READS: Record<
  string,
  { calls: SdkName[]; empty: unknown[]; loading: string; emptyCopy: string; errorCopy: string }
> = {
  'findings-summary': {
    calls: ['facetFindingsApiV1FindingsFacetsGet'],
    empty: [{ facets: {} }],
    loading: 'Loading findings summary',
    emptyCopy: 'No findings at this time.',
    errorCopy: 'Findings summary unavailable.',
  },
  'package-type': {
    calls: ['facetFindingsApiV1FindingsFacetsGet'],
    empty: [{ facets: {} }],
    loading: 'Loading package types',
    emptyCopy: 'Awaiting package-type data.',
    errorCopy: 'Package-type counts unavailable.',
  },
  'findings-by-namespace': {
    calls: ['facetFindingsApiV1FindingsFacetsGet'],
    empty: [{ facets: {} }],
    loading: 'Loading namespaces',
    emptyCopy: 'No namespace data in range.',
    errorCopy: 'Namespace counts unavailable.',
  },
  'riskiest-images': {
    calls: ['listRunningImagesApiV1ImagesGet'],
    empty: [{ inventory: INVENTORY, images: [] }],
    loading: 'Loading riskiest images',
    emptyCopy: 'No image findings in the running inventory.',
    errorCopy: 'Riskiest images unavailable.',
  },
  'handled-findings': {
    calls: ['contributorsApiV1ContributorsGet'],
    empty: [{ handled_over_time: [] }],
    loading: 'Loading handled findings',
    emptyCopy: 'No findings were handled in this window.',
    errorCopy: 'Handled-findings activity unavailable.',
  },
  'top-components': {
    calls: ['topComponentsFindingsApiV1FindingsTopComponentsGet'],
    empty: [{ components: [] }],
    loading: 'Loading top components',
    emptyCopy: 'No component data yet.',
    errorCopy: 'Component ranking unavailable.',
  },
  'scan-ingest': {
    calls: ['scansTrendApiV1TrendsScansGet', 'scannerFreshnessApiV1ScannersFreshnessGet'],
    empty: [{ series: {} }, { scanners: [] }],
    loading: 'Loading ingest activity',
    emptyCopy: 'No scans committed in this range',
    errorCopy: 'Ingest activity unavailable.',
  },
  'failed-ingests': {
    calls: ['ingestFailuresTrendApiV1TrendsIngestFailuresGet'],
    empty: [{ series: {} }],
    loading: 'Loading failed ingests',
    emptyCopy: 'No refused pushes in this range.',
    errorCopy: 'Failed-ingest activity unavailable.',
  },
  'triage-activity': {
    calls: ['auditFacetsApiV1AuditFacetsGet'],
    empty: [{ activity: [] }],
    loading: 'Loading audit activity',
    emptyCopy: 'Nobody changed a finding in this range.',
    errorCopy: 'Audit activity unavailable.',
  },
  'triage-progress': {
    calls: ['facetFindingsApiV1FindingsFacetsGet'],
    empty: [{ facets: { severity: [] } }],
    loading: 'Loading triage progress',
    emptyCopy: 'No findings in the store yet.',
    errorCopy: 'Triage progress unavailable.',
  },
}

const fn = (name: SdkName) => vi.mocked(sdk[name] as (...a: unknown[]) => Promise<unknown>)

function mountPanel(panel: CatalogPanel, c: PanelContext = ctx()) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
  })
  return mount(panel.component, {
    props: panel.props(c),
    global: { plugins: [router], stubs: { EChart: true, GuideLink: true } },
  })
}

/** an answer that the test lets in later; afterEach lets every one in, so no read stays open */
let pending: ((v: unknown) => void)[] = []
const later = () => new Promise((r) => void pending.push(r))

beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  // the panels that read the app's cluster read the same one the dashboard passes
  useClusterStore().selectedId = CLUSTER
})
afterEach(async () => {
  for (const r of pending) r(refused())
  pending = []
  await flushPromises()
})

describe('the catalog', () => {
  it('holds each panel once, with a stable id, a name, a group and one line', () => {
    const ids = PANELS.map((p) => p.id)
    expect(new Set(ids).size).toBe(ids.length)
    for (const p of PANELS) {
      expect(p.id).toMatch(/^[a-z]+(-[a-z]+)*$/)
      expect(p.name.length).toBeGreaterThan(0)
      expect(['Findings', 'Scanners', 'People']).toContain(p.group)
      expect(p.line).toMatch(/\.$/)
      expect([1, 2]).toContain(p.defaultWidth)
    }
    expect(new Set(PANELS.map((p) => p.name)).size).toBe(PANELS.length)
  })

  it('gives each panel at least one height, short or tall, in whole grid rows', () => {
    for (const p of PANELS) {
      const hs = heightsOf(p)
      expect(hs.length).toBeGreaterThan(0)
      for (const h of hs) {
        expect(['short', 'tall']).toContain(h)
        expect(Number.isInteger(p.heights[h])).toBe(true)
      }
    }
    // a tall panel is taller than the same panel short
    for (const p of PANELS.filter((x) => x.heights.short && x.heights.tall)) {
      expect(p.heights.tall!).toBeGreaterThan(p.heights.short!)
    }
  })

  it('finds a panel by its id, and nothing for an unknown id', () => {
    expect(panelById('top-components')?.name).toBe('Top components')
    expect(panelById('no-such-panel')).toBeUndefined()
  })

  it('lists the read and the copy of every panel in this spec', () => {
    expect(Object.keys(READS).sort()).toEqual(PANELS.map((p) => p.id).sort())
  })

  it('adds as_of to the global query only at a past time', () => {
    expect(globalQuery(ctx())).toEqual({ cluster_id: CLUSTER })
    expect(globalQuery(ctx({ t: '2026-10-01T00:00:00Z' }))).toEqual({
      cluster_id: CLUSTER,
      as_of: '2026-10-01T00:00:00Z',
    })
  })
})

describe.each(PANELS.map((p) => [p.id, p] as const))('panel %s, on a page that gives it nothing', (id, panel) => {
  const reads = READS[id]!

  it('sends its own request for the cluster, and shows a loading state before the answer', async () => {
    for (const name of reads.calls) fn(name).mockImplementation(later)
    const w = mountPanel(panel)
    await flushPromises()
    for (const name of reads.calls) {
      expect(fn(name)).toHaveBeenCalled()
      expect(fn(name).mock.calls[0]![0]).toMatchObject({ query: { cluster_id: CLUSTER } })
    }
    expect(w.find(`[aria-label="${reads.loading}"]`).exists()).toBe(true)
    // no claim before evidence
    expect(w.text()).not.toContain(reads.emptyCopy)
    expect(w.text()).not.toContain(reads.errorCopy)
  })

  it('says so when the answer is empty', async () => {
    reads.calls.forEach((name, i) => fn(name).mockResolvedValue(ok(reads.empty[i])))
    const w = mountPanel(panel)
    await flushPromises()
    expect(w.text()).toContain(reads.emptyCopy)
    expect(w.text()).not.toContain(reads.errorCopy)
  })

  it('shows its error when the read fails', async () => {
    for (const name of reads.calls) fn(name).mockResolvedValue(refused())
    const w = mountPanel(panel)
    await flushPromises()
    expect(w.text()).toContain(reads.errorCopy)
  })
})

describe('settings a panel takes from the dashboard', () => {
  const components = (n: number) =>
    Array.from({ length: n }, (_, i) => ({
      package_name: `pkg-${i}`,
      count: 100 - i,
      unique_cves_by_scanner: { trivy: 100 - i, grype: i % 3 },
    }))

  it.each([
    ['short', TABLE_ROWS.short],
    ['tall', TABLE_ROWS.tall],
  ] as const)('a %s table panel shows %i rows a page', async (height, rows) => {
    fn('topComponentsFindingsApiV1FindingsTopComponentsGet').mockResolvedValue(
      ok({ components: components(40) }),
    )
    const w = mountPanel(panelById('top-components')!, ctx({ height }))
    await flushPromises()
    expect(w.findAll('tbody tr')).toHaveLength(rows)
  })

  it.each(['all', 'trivy', 'grype'] as const)('the %s scanner value reaches the panel', async (scanner) => {
    fn('topComponentsFindingsApiV1FindingsTopComponentsGet').mockResolvedValue(
      ok({ components: [{ package_name: 'openssl', count: 9, unique_cves_by_scanner: { trivy: 4, grype: 2 } }] }),
    )
    const w = mountPanel(panelById('top-components')!, ctx({ scanner }))
    await flushPromises()
    // per scanner, never merged: `all` adds the two scanners' own counts
    const expected = { all: '6', trivy: '4', grype: '2' }[scanner]
    expect(w.find('tbody tr td:last-child').text()).toBe(expected)
  })

  it('sends the dashboard time to a panel that reads at a past time', async () => {
    fn('auditFacetsApiV1AuditFacetsGet').mockResolvedValue(ok({ activity: [] }))
    mountPanel(panelById('triage-activity')!, ctx({ t: '2026-10-01T00:00:00Z' }))
    await flushPromises()
    expect(fn('auditFacetsApiV1AuditFacetsGet').mock.calls[0]![0]).toMatchObject({
      query: { cluster_id: CLUSTER, as_of: '2026-10-01T00:00:00Z', entity_type: ['finding', 'decision'] },
    })
  })
})

describe('the panel frame', () => {
  it('shows the name, the line and the panel', () => {
    const w = mount(PanelFrame, {
      props: { title: 'Triage progress', line: 'For each severity, how many findings people have triaged.' },
      slots: { default: '<div class="one">part one</div><div class="two">part two</div>' },
    })
    expect(w.find('h2').text()).toBe('Triage progress')
    expect(w.text()).toContain('how many findings people have triaged')
    // a panel made of two parts keeps both
    expect(w.find('.one').exists() && w.find('.two').exists()).toBe(true)
  })

  it('does not clip: the card draws its own shadow outside its box', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/components/dashboards/PanelFrame.vue'), 'utf8')
    const style = source.slice(source.indexOf('<style'))
    expect(style).not.toMatch(/overflow(-[xy])?\s*:|contain\s*:|clip-path\s*:/)
    expect(style).not.toMatch(/height\s*:\s*100%/)
  })

  it('frames only the panels that have no card of their own', () => {
    expect(PANELS.filter((p) => p.framed).map((p) => p.id)).toEqual(['triage-progress'])
  })
})

const bucket = (key: string, trivy: number, grype: number) => ({
  key,
  count: trivy + grype,
  by_scanner: { trivy, grype },
})
const FACETS = {
  present: [bucket('true', 30, 12)],
  severity: [bucket('critical', 5, 2), bucket('high', 9, 4)],
  fixable: [bucket('true', 10, 3)],
  ptype: [bucket('debian', 20, 10), bucket('npm', 10, 2)],
  namespaces: Array.from({ length: 30 }, (_, i) => bucket(`ns-${String(i).padStart(2, '0')}`, 30 - i, 0)),
}
const facetsMock = () => fn('facetFindingsApiV1FindingsFacetsGet')

describe('a panel that its screen can feed', () => {
  it.each([
    ['the findings summary', OverviewStatBands],
    ['the package types', PackageTypeCard],
    ['the namespaces', OverviewNamespacesCard],
  ] as const)('%s uses the facets the screen passes and sends no request', async (_name, component) => {
    const w = mount(component, {
      props: { scanner: 'all', facets: FACETS },
      global: { plugins: [createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })], stubs: { EChart: true } },
    })
    await flushPromises()
    expect(facetsMock()).not.toHaveBeenCalled()
    expect(w.text()).not.toMatch(/unavailable|Loading/)
  })

  it('three facet panels on one dashboard share one read', async () => {
    facetsMock().mockImplementation(later)
    for (const id of ['findings-summary', 'package-type', 'findings-by-namespace']) mountPanel(panelById(id)!)
    await flushPromises()
    expect(facetsMock()).toHaveBeenCalledTimes(1)
  })

  /** a facets panel mounted with its own query: the whole query is the request (issue 999) */
  function mountWithQuery(component: typeof OverviewStatBands | typeof PackageTypeCard, query: Record<string, unknown>) {
    return mount(component, {
      props: { scanner: 'all', query: query as never },
      global: { plugins: [createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }] })], stubs: { EChart: true } },
    })
  }

  it('two panels with different filters send two reads, each with its own filters', async () => {
    facetsMock().mockImplementation(later)
    mountWithQuery(OverviewStatBands, { cluster_id: CLUSTER, exclude_namespace: ['kube-system'], all_filters: true })
    mountWithQuery(PackageTypeCard, { cluster_id: CLUSTER, severity: ['critical'], all_filters: true })
    await flushPromises()
    expect(facetsMock()).toHaveBeenCalledTimes(2)
    const sent = facetsMock().mock.calls.map((c) => (c[0] as { query: unknown }).query)
    expect(sent).toContainEqual({ cluster_id: CLUSTER, exclude_namespace: ['kube-system'], all_filters: true })
    expect(sent).toContainEqual({ cluster_id: CLUSTER, severity: ['critical'], all_filters: true })
  })

  it('two panels with the same filters share one read, whatever the order of the params', async () => {
    facetsMock().mockImplementation(later)
    mountWithQuery(OverviewStatBands, { cluster_id: CLUSTER, severity: ['critical'], all_filters: true })
    mountWithQuery(PackageTypeCard, { all_filters: true, severity: ['critical'], cluster_id: CLUSTER })
    await flushPromises()
    expect(facetsMock()).toHaveBeenCalledTimes(1)
  })

  it('a second ask after the read came back reads again', async () => {
    facetsMock().mockResolvedValue(ok({ facets: FACETS }))
    mountPanel(panelById('findings-summary')!)
    await flushPromises()
    mountPanel(panelById('package-type')!)
    await flushPromises()
    expect(facetsMock()).toHaveBeenCalledTimes(2)
  })

  it('Handled findings uses the Contributors series and sends no request', async () => {
    const w = mount(ContributorsLens, {
      props: { series: [], settled: true, failed: false },
      global: { stubs: { EChart: true } },
    })
    await flushPromises()
    expect(fn('contributorsApiV1ContributorsGet')).not.toHaveBeenCalled()
    // on Contributors the board under the strip is empty too; a dashboard has no board
    expect(w.text()).toContain('The board below is empty too.')
  })

  it('Handled findings on a dashboard reads the window and says nothing of a board', async () => {
    fn('contributorsApiV1ContributorsGet').mockResolvedValue(ok({ handled_over_time: [] }))
    const w = mountPanel(panelById('handled-findings')!, ctx({ windowDays: 7 }))
    await flushPromises()
    expect(fn('contributorsApiV1ContributorsGet').mock.calls[0]![0]).toMatchObject({
      query: { cluster_id: CLUSTER, days: 7 },
    })
    expect(w.text()).not.toContain('board below')
  })
})

describe('the findings summary on a dashboard', () => {
  it('shows both of its bands', async () => {
    facetsMock().mockResolvedValue(ok({ facets: FACETS }))
    const w = mountPanel(panelById('findings-summary')!)
    await flushPromises()
    expect(w.findAll('.stat-band')).toHaveLength(2)
  })

  it.each([
    ['all', '7'],
    ['trivy', '5'],
    ['grype', '2'],
  ] as const)('counts critical under the %s scanner value', async (scanner, critical) => {
    facetsMock().mockResolvedValue(ok({ facets: FACETS }))
    const w = mountPanel(panelById('findings-summary')!, ctx({ scanner }))
    await flushPromises()
    expect(w.find('.stat-cell .stat-num').text()).toBe(critical)
  })

  it('one scanner with no findings shows its zeros, not the empty copy', async () => {
    facetsMock().mockResolvedValue(
      ok({ facets: { ...FACETS, present: [bucket('true', 0, 12)], severity: [bucket('critical', 0, 2)] } }),
    )
    const w = mountPanel(panelById('findings-summary')!, ctx({ scanner: 'trivy' }))
    await flushPromises()
    expect(w.text()).not.toContain('No findings at this time.')
    expect(w.find('.stat-cell .stat-num').text()).toBe('0')
  })
})

describe('a table panel takes its rows from its height', () => {
  it.each([
    ['short', TABLE_ROWS.short],
    ['tall', TABLE_ROWS.tall],
  ] as const)('Findings by namespace, %s, lists %i namespaces', async (height, rows) => {
    facetsMock().mockResolvedValue(ok({ facets: FACETS }))
    const w = mountPanel(panelById('findings-by-namespace')!, ctx({ height }))
    await flushPromises()
    expect(w.findAll('tbody tr')).toHaveLength(rows)
    expect(w.text()).toContain(`top ${rows} by findings`)
  })

  it.each([
    ['short', TABLE_ROWS.short],
    ['tall', TABLE_ROWS.tall],
  ] as const)('Riskiest images, %s, shows %i rows a page', async (height, rows) => {
    const images = Array.from({ length: 40 }, (_, i) => ({
      image_digest: `sha256:${i}`,
      image_repo: `repo-${i}`,
      tag: 'v1',
      severity_by_scanner: { trivy: { crit: 40 - i, high: 1, med: 0, low: 0, negligible: 0, unknown: 0, total: 41 - i, fixable: 0 } },
    }))
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(ok({ inventory: null, images }))
    const w = mountPanel(panelById('riskiest-images')!, ctx({ height }))
    await flushPromises()
    expect(w.findAll('tbody tr')).toHaveLength(rows)
  })
})

describe('Overview, after its panels moved into the catalog', () => {
  it('reads the findings facets once for the summary, the package types and the namespaces', async () => {
    facetsMock().mockResolvedValue(ok({ facets: FACETS }))
    fn('findingsTrendApiV1TrendsFindingsGet').mockResolvedValue(ok({ new: {}, resolved: {} }))
    fn('scannerFreshnessApiV1ScannersFreshnessGet').mockResolvedValue(ok({ scanners: [] }))
    fn('scansTrendApiV1TrendsScansGet').mockResolvedValue(ok({ series: {} }))
    fn('topComponentsFindingsApiV1FindingsTopComponentsGet').mockResolvedValue(ok({ components: [] }))
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(ok({ inventory: null, images: [] }))
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }] })
    const w = mount(OverviewView, { global: { plugins: [router], stubs: { EChart: true, GuideLink: true } } })
    await flushPromises()
    expect(facetsMock()).toHaveBeenCalledTimes(1)
    // the three panels drew from that one read
    expect(w.findAll('.stat-band')).toHaveLength(2)
    expect(w.text()).toContain('Package type')
    expect(w.text()).toContain('ns-00')
  })
})

/** a reply the test lets in by hand, in any order */
function deferred() {
  let resolve!: (v: unknown) => void
  const promise = new Promise((r) => (resolve = r))
  return { promise, resolve }
}

describe('a newer read wins: a slow answer for the old cluster never shows under the new one', () => {
  it('Top components', async () => {
    const a = deferred()
    const b = deferred()
    fn('topComponentsFindingsApiV1FindingsTopComponentsGet').mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const w = mountPanel(panelById('top-components')!)
    await flushPromises()
    useClusterStore().selectedId = 'c-other'
    await flushPromises()
    b.resolve(ok({ components: [{ package_name: 'pkg-of-b', count: 1, unique_cves_by_scanner: { trivy: 1 } }] }))
    await flushPromises()
    a.resolve(ok({ components: [{ package_name: 'pkg-of-a', count: 1, unique_cves_by_scanner: { trivy: 1 } }] }))
    await flushPromises()
    expect(w.text()).toContain('pkg-of-b')
    expect(w.text()).not.toContain('pkg-of-a')
  })

  it('Top components, after a switch made at a past time and a return to now', async () => {
    const timeTravel = (await import('@/stores/timeTravel')).useTimeTravelStore()
    fn('topComponentsFindingsApiV1FindingsTopComponentsGet')
      .mockResolvedValueOnce(ok({ components: [{ package_name: 'pkg-of-a', count: 1, unique_cves_by_scanner: { trivy: 1 } }] }))
      .mockReturnValueOnce(later())
    const w = mountPanel(panelById('top-components')!)
    await flushPromises()
    expect(w.text()).toContain('pkg-of-a')
    timeTravel.rewindTo('2026-10-01T00:00:00.000Z')
    await flushPromises()
    useClusterStore().selectedId = 'c-other'
    await flushPromises()
    timeTravel.backToNow()
    await flushPromises()
    // B's read is open: A's rows must already be gone
    expect(w.text()).not.toContain('pkg-of-a')
    expect(w.find('[aria-label="Loading top components"]').exists()).toBe(true)
  })

  it('Riskiest images', async () => {
    const a = deferred()
    const b = deferred()
    fn('listRunningImagesApiV1ImagesGet').mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const image = (repo: string) => ({
      image_digest: `sha256:${repo}`,
      image_repo: repo,
      tag: 'v1',
      severity_by_scanner: { trivy: { crit: 1, high: 0, med: 0, low: 0, negligible: 0, unknown: 0, total: 1, fixable: 0 } },
    })
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    useClusterStore().selectedId = 'c-other'
    await flushPromises()
    b.resolve(ok({ inventory: INVENTORY, images: [image('repo-of-b')] }))
    await flushPromises()
    a.resolve(ok({ inventory: INVENTORY, images: [image('repo-of-a')] }))
    await flushPromises()
    expect(w.text()).toContain('repo-of-b')
    expect(w.text()).not.toContain('repo-of-a')
  })

  it('Handled findings', async () => {
    const a = deferred()
    const b = deferred()
    fn('contributorsApiV1ContributorsGet').mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const panel = panelById('handled-findings')!
    const w = mountPanel(panel)
    await flushPromises()
    await w.setProps(panel.props(ctx({ clusterId: 'c-other' })))
    b.resolve(ok({ handled_over_time: [] }))
    await flushPromises()
    a.resolve(ok({ handled_over_time: [{ date: '2026-10-01T00:00:00.000Z', count: 5 }] }))
    await flushPromises()
    expect(w.text()).toContain('No findings were handled in this window.')
  })

  it('a facets panel', async () => {
    const a = deferred()
    const b = deferred()
    facetsMock().mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const panel = panelById('findings-summary')!
    const w = mountPanel(panel)
    await flushPromises()
    await w.setProps(panel.props(ctx({ clusterId: 'c-other' })))
    b.resolve(ok({ facets: {} }))
    await flushPromises()
    a.resolve(ok({ facets: FACETS }))
    await flushPromises()
    expect(w.text()).toContain('No findings at this time.')
    expect(w.findAll('.stat-band')).toHaveLength(0)
  })

  it('a facets panel drops the old cluster\'s counts while the new read is open', async () => {
    facetsMock().mockResolvedValueOnce(ok({ facets: FACETS })).mockReturnValueOnce(later())
    const panel = panelById('findings-summary')!
    const w = mountPanel(panel)
    await flushPromises()
    expect(w.findAll('.stat-band')).toHaveLength(2)
    await w.setProps(panel.props(ctx({ clusterId: 'c-other' })))
    expect(w.findAll('.stat-band')).toHaveLength(0)
    expect(w.find('[aria-label="Loading findings summary"]').exists()).toBe(true)
  })
})

describe('a read still open when no read is due never lands later', () => {
  it('Top components: A stays open across a rewind and a switch to B at a past time', async () => {
    const timeTravel = (await import('@/stores/timeTravel')).useTimeTravelStore()
    const a = deferred()
    fn('topComponentsFindingsApiV1FindingsTopComponentsGet').mockReturnValueOnce(a.promise).mockReturnValueOnce(later())
    const w = mountPanel(panelById('top-components')!)
    await flushPromises()
    timeTravel.rewindTo('2026-10-01T00:00:00.000Z')
    await flushPromises()
    useClusterStore().selectedId = 'c-other'
    await flushPromises()
    a.resolve(ok({ components: [{ package_name: 'pkg-of-a', count: 1, unique_cves_by_scanner: { trivy: 1 } }] }))
    await flushPromises()
    timeTravel.backToNow()
    await flushPromises()
    // B's read is open under c-other: A's rows must not show
    expect(w.text()).not.toContain('pkg-of-a')
    expect(w.find('[aria-label="Loading top components"]').exists()).toBe(true)
  })

  it('Riskiest images: the images of a cluster leave with it', async () => {
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValueOnce(
      ok({ inventory: INVENTORY, images: [{ image_digest: 'sha256:a', image_repo: 'repo-of-a', tag: 'v1', severity_by_scanner: { trivy: { crit: 1, high: 0, med: 0, low: 0, negligible: 0, unknown: 0, total: 1, fixable: 0 } } }] }),
    )
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    expect(w.text()).toContain('repo-of-a')
    useClusterStore().selectedId = null
    await flushPromises()
    expect(w.text()).not.toContain('repo-of-a')
  })

  it('Riskiest images: the selected cluster goes away while its read is open', async () => {
    const a = deferred()
    fn('listRunningImagesApiV1ImagesGet').mockReturnValueOnce(a.promise)
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    useClusterStore().selectedId = null
    await flushPromises()
    a.resolve(ok({ inventory: INVENTORY, images: [{ image_digest: 'sha256:a', image_repo: 'repo-of-a', tag: 'v1' }] }))
    await flushPromises()
    expect(w.text()).not.toContain('repo-of-a')
    expect(w.find('[aria-label="Loading riskiest images"]').exists()).toBe(true)
  })

  it('a facets panel: the query goes away and comes back while the first read is open', async () => {
    const a = deferred()
    facetsMock().mockReturnValueOnce(a.promise).mockReturnValueOnce(later())
    const panel = panelById('findings-summary')!
    const w = mountPanel(panel)
    await flushPromises()
    await w.setProps({ query: null })
    a.resolve(ok({ facets: FACETS }))
    await flushPromises()
    await w.setProps(panel.props(ctx()))
    await flushPromises()
    // the second read is open: the answer to the first one must not show as if it were its own
    expect(w.findAll('.stat-band')).toHaveLength(0)
    expect(w.find('[aria-label="Loading findings summary"]').exists()).toBe(true)
  })

  it('Handled findings: the query goes away and comes back while the first read is open', async () => {
    const a = deferred()
    fn('contributorsApiV1ContributorsGet').mockReturnValueOnce(a.promise).mockReturnValueOnce(later())
    const panel = panelById('handled-findings')!
    const w = mountPanel(panel)
    await flushPromises()
    await w.setProps({ query: null })
    a.resolve(ok({ handled_over_time: [] }))
    await flushPromises()
    await w.setProps(panel.props(ctx()))
    await flushPromises()
    expect(w.text()).not.toContain('No findings were handled in this window.')
    expect(w.find('[aria-label="Loading handled findings"]').exists()).toBe(true)
  })
})

describe('Riskiest images with no committed inventory', () => {
  it('says that no inventory is committed yet, not that the cluster has no findings', async () => {
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(ok({ inventory: null, images: [] }))
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    expect(w.text()).toContain('No inventory committed yet. Images show once a scanner cycle completes.')
    expect(w.text()).not.toContain('No image findings')
  })

  it('names the time of its answer, not a time whose read is still open', async () => {
    const timeTravel = (await import('@/stores/timeTravel')).useTimeTravelStore()
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValueOnce(ok({ inventory: null, images: [] })).mockReturnValueOnce(later())
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    timeTravel.rewindTo('2026-10-01T00:00:00.000Z')
    await flushPromises()
    expect(w.text()).toContain('No inventory committed yet.')
    expect(w.text()).not.toContain('at this point in time')
  })

  it('a committed inventory of the next cluster ends the no-inventory text', async () => {
    fn('listRunningImagesApiV1ImagesGet')
      .mockResolvedValueOnce(ok({ inventory: null, images: [] }))
      .mockResolvedValueOnce(ok({ inventory: INVENTORY, images: [] }))
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    expect(w.text()).toContain('No inventory committed yet.')
    useClusterStore().selectedId = 'c-other'
    await flushPromises()
    expect(w.text()).toContain('No image findings in the running inventory.')
    expect(w.text()).not.toContain('No inventory committed')
  })

  it('a failed read after a no-inventory answer shows the error', async () => {
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValueOnce(ok({ inventory: null, images: [] })).mockResolvedValueOnce(refused())
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    useClusterStore().selectedId = 'c-other'
    await flushPromises()
    expect(w.text()).toContain('Riskiest images unavailable.')
    expect(w.text()).not.toContain('No inventory committed')
  })

  it('at a past time before the first inventory, says so for that time', async () => {
    const timeTravel = (await import('@/stores/timeTravel')).useTimeTravelStore()
    timeTravel.rewindTo('2026-10-01T00:00:00.000Z')
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(ok({ inventory: null, images: [] }))
    const w = mountPanel(panelById('riskiest-images')!, ctx({ t: '2026-10-01T00:00:00.000Z' }))
    await flushPromises()
    expect(w.text()).toContain('No inventory committed at this point in time.')
  })
})

describe('an equal query rebuilt by the dashboard starts no new read', () => {
  it('a scanner toggle on a facets panel re-reads nothing', async () => {
    facetsMock().mockResolvedValue(ok({ facets: FACETS }))
    const panel = panelById('findings-summary')!
    const w = mountPanel(panel)
    await flushPromises()
    await w.setProps(panel.props(ctx({ scanner: 'trivy' })))
    await w.setProps(panel.props(ctx({ scanner: 'grype' })))
    await flushPromises()
    expect(facetsMock()).toHaveBeenCalledTimes(1)
  })

  it('Handled findings re-reads nothing when the dashboard rebuilds its props', async () => {
    fn('contributorsApiV1ContributorsGet').mockResolvedValue(ok({ handled_over_time: [] }))
    const panel = panelById('handled-findings')!
    const w = mountPanel(panel)
    await flushPromises()
    await w.setProps(panel.props(ctx({ scanner: 'trivy' })))
    await flushPromises()
    expect(fn('contributorsApiV1ContributorsGet')).toHaveBeenCalledTimes(1)
  })
})

describe('each scanner value reaches the other scanner panels', () => {
  it.each([
    ['all', '42'],
    ['trivy', '30'],
    ['grype', '12'],
  ] as const)('Package type, Per namespace and Riskiest images count under %s', async (scanner, debianNs) => {
    facetsMock().mockResolvedValue(
      ok({ facets: { ...FACETS, ptype: [bucket('debian', 30, 12)], namespaces: [bucket('team-a', 30, 12)] } }),
    )
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(
      ok({
        inventory: INVENTORY,
        images: [
          {
            image_digest: 'sha256:1',
            image_repo: 'repo',
            tag: 'v1',
            severity_by_scanner: {
              trivy: { crit: 30, high: 0, med: 0, low: 0, negligible: 0, unknown: 0, total: 30, fixable: 0 },
              grype: { crit: 12, high: 0, med: 0, low: 0, negligible: 0, unknown: 0, total: 12, fixable: 0 },
            },
          },
        ],
      }),
    )
    const pt = mountPanel(panelById('package-type')!, ctx({ scanner }))
    const ns = mountPanel(panelById('findings-by-namespace')!, ctx({ scanner }))
    const ri = mountPanel(panelById('riskiest-images')!, ctx({ scanner }))
    await flushPromises()
    expect(pt.find('.donut-row b').text()).toBe(debianNs)
    expect(ns.find('tbody tr td:last-child').text()).toBe(debianNs)
    expect(ri.find('tbody tr td:nth-child(2)').text()).toBe(debianNs)
  })
})

describe('a panel with filters (issue 999)', () => {
  // a stored filters object, as the backend keeps it (`present: true` is the ViewPreset default).
  // The flag is on no row, so each link must carry a panel filter that its row does not set.
  const FILTERS = { present: true, exclude_namespace: ['kube-system'], kev: true }
  const filtered = ctx({ filters: FILTERS as never })

  /** each panel that takes filters, an answer that draws a row, and the element a click opens */
  const CASES: Record<string, { answers: unknown[]; click: string; row: Record<string, string> }> = {
    'findings-summary': { answers: [{ facets: FACETS }], click: '.stat-cell', row: { severity: 'critical' } },
    'package-type': { answers: [{ facets: FACETS }], click: '.donut-row', row: { ptype: 'debian' } },
    'findings-by-namespace': { answers: [{ facets: FACETS }], click: 'tbody tr', row: { namespace: 'ns-00' } },
    'top-components': {
      answers: [{ components: [{ package_name: 'openssl', count: 4, unique_cves_by_scanner: { trivy: 3 } }] }],
      click: 'tbody tr',
      row: { q: 'openssl' },
    },
    'triage-progress': {
      answers: [{ facets: { severity: [bucket('high', 9, 4)] } }, { facets: { severity: [bucket('high', 3, 1)] } }],
      click: '.prog-row',
      row: { severity: 'high', state: 'open,stale' },
    },
  }

  function mountFiltered(id: string) {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/:any(.*)*', name: 'findings', component: { template: '<div />' } }],
    })
    const panel = panelById(id)!
    const w = mount(panel.component, {
      props: panel.props(filtered),
      global: { plugins: [router], stubs: { EChart: true, GuideLink: true } },
    })
    return { w, router }
  }

  it('covers every panel that takes filters', () => {
    expect(Object.keys(CASES).sort()).toEqual(PANELS.filter((p) => p.takesFilters).map((p) => p.id).sort())
  })

  it.each(Object.keys(CASES))('%s sends its filters, with all_filters, in each read', async (id) => {
    const c = CASES[id]!
    const calls = READS[id]!.calls
    for (const name of new Set(calls)) {
      for (const a of c.answers) fn(name).mockResolvedValueOnce(ok(a))
    }
    mountFiltered(id)
    await flushPromises()
    const sent = calls.flatMap((name) => fn(name).mock.calls.map((call) => (call[0] as { query: object }).query))
    expect(sent.length).toBeGreaterThan(0)
    for (const q of sent) {
      expect(q).toMatchObject({ cluster_id: CLUSTER, exclude_namespace: ['kube-system'], kev: true, all_filters: true })
    }
  })

  it.each(Object.keys(CASES))('%s opens Findings with its filters and the value of the row', async (id) => {
    const c = CASES[id]!
    for (const name of new Set(READS[id]!.calls)) {
      for (const a of c.answers) fn(name).mockResolvedValueOnce(ok(a))
    }
    const { w, router } = mountFiltered(id)
    await flushPromises()
    await w.find(c.click).trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ namespace: '!kube-system', attr: 'kev', ...c.row })
  })

  it('a panel with no filters reads and links as before', async () => {
    facetsMock().mockResolvedValue(ok({ facets: FACETS }))
    const panel = panelById('findings-by-namespace')!
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }] })
    const w = mount(panel.component, { props: panel.props(ctx({ filters: null })), global: { plugins: [router] } })
    await flushPromises()
    expect((facetsMock().mock.calls[0]![0] as { query: object }).query).toEqual({ cluster_id: CLUSTER })
    await w.find('tbody tr').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ namespace: 'ns-00' })
  })

  it('"New in range" reads in the range of the dashboard, not in the stored days', async () => {
    facetsMock().mockResolvedValue(ok({ facets: FACETS }))
    const [placed] = placePanels([
      { panel: 'findings-by-namespace', x: 0, y: 0, w: 1, h: 'short', filters: { present: true, new_within_days: 7 } },
    ])
    const props = panelPropsCache()('0-0', placed!, { clusterId: CLUSTER, t: null, windowDays: 30, scanner: 'all' })
    mount(panelById('findings-by-namespace')!.component, { props, global: { stubs: { EChart: true } } })
    await flushPromises()
    expect((facetsMock().mock.calls[0]![0] as { query: object }).query).toMatchObject({ new_within_days: 30, all_filters: true })
  })
})

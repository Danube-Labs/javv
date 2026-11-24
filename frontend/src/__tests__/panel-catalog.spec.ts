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
    topImagesFindingsApiV1FindingsTopImagesGet: vi.fn<() => Promise<unknown>>(),
    contributorsApiV1ContributorsGet: vi.fn<() => Promise<unknown>>(),
    findingsTrendApiV1TrendsFindingsGet: vi.fn<() => Promise<unknown>>(),
    topValuesFindingsApiV1FindingsTopValuesGet: vi.fn<() => Promise<unknown>>(),
    newFindingsTrendApiV1TrendsNewFindingsGet: vi.fn<() => Promise<unknown>>(),
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
import { useTimeTravelStore } from '@/stores/timeTravel'
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
    errorCopy: 'JAVV cannot show the findings summary. Check the backend connection.',
  },
  'findings-over-time': {
    calls: ['findingsTrendApiV1TrendsFindingsGet'],
    empty: [{ new: {}, resolved: {} }],
    loading: 'Loading vulnerabilities over time',
    emptyCopy: 'No new or resolved findings in this range.',
    errorCopy: 'JAVV cannot show the findings over time. Check the backend connection.',
  },
  'package-type': {
    calls: ['facetFindingsApiV1FindingsFacetsGet'],
    empty: [{ facets: {} }],
    loading: 'Loading package types',
    emptyCopy: 'No package types yet.',
    errorCopy: 'JAVV cannot show the package types. Check the backend connection.',
  },
  'findings-by-namespace': {
    calls: ['facetFindingsApiV1FindingsFacetsGet'],
    empty: [{ facets: {} }],
    loading: 'Loading namespaces',
    emptyCopy: 'No namespaces in this range.',
    errorCopy: 'JAVV cannot show the namespaces. Check the backend connection.',
  },
  'riskiest-images': {
    calls: ['listRunningImagesApiV1ImagesGet'],
    empty: [{ inventory: INVENTORY, images: [] }],
    loading: 'Loading riskiest images',
    emptyCopy: 'The running images have no findings.',
    errorCopy: 'JAVV cannot show the riskiest images. Check the backend connection.',
  },
  'handled-findings': {
    calls: ['contributorsApiV1ContributorsGet'],
    empty: [{ handled_over_time: [] }],
    loading: 'Loading handled findings',
    emptyCopy: 'Nobody handled a finding in this range.',
    errorCopy: 'JAVV cannot show the handled findings. Check the backend connection.',
  },
  'top-components': {
    calls: ['topComponentsFindingsApiV1FindingsTopComponentsGet'],
    empty: [{ components: [] }],
    loading: 'Loading top components',
    emptyCopy: 'No components yet.',
    errorCopy: 'JAVV cannot show the top components. Check the backend connection.',
  },
  'top-cves': {
    calls: ['topValuesFindingsApiV1FindingsTopValuesGet'],
    empty: [{ by: 'cve_id', values: [] }],
    loading: 'Loading top vulnerabilities',
    emptyCopy: 'No vulnerabilities yet.',
    errorCopy: 'JAVV cannot show the top vulnerabilities. Check the backend connection.',
  },
  'new-findings': {
    calls: ['newFindingsTrendApiV1TrendsNewFindingsGet'],
    empty: [{ series: {}, days: 30, interval: 'day' }],
    loading: 'Loading the new findings',
    emptyCopy: 'No new findings in this range.',
    errorCopy: 'JAVV cannot show the new findings. Check the backend connection.',
  },
  'scan-ingest': {
    calls: ['scansTrendApiV1TrendsScansGet', 'scannerFreshnessApiV1ScannersFreshnessGet'],
    empty: [{ series: {} }, { scanners: [] }],
    loading: 'Loading the scans',
    emptyCopy: 'No scans in this range',
    errorCopy: 'JAVV cannot show the scans. Check the backend connection.',
  },
  'failed-ingests': {
    calls: ['ingestFailuresTrendApiV1TrendsIngestFailuresGet'],
    empty: [{ series: {} }],
    loading: 'Loading the refused scans',
    emptyCopy: 'No refused scans in this range.',
    errorCopy: 'JAVV cannot show the refused scans. Check the backend connection.',
  },
  'triage-activity': {
    calls: ['auditFacetsApiV1AuditFacetsGet'],
    empty: [{ activity: [] }],
    loading: 'Loading audit activity',
    emptyCopy: 'Nobody changed a finding in this range.',
    errorCopy: 'JAVV cannot show the audit activity. Check the backend connection.',
  },
  'triage-progress': {
    calls: ['facetFindingsApiV1FindingsFacetsGet'],
    empty: [{ facets: { severity: [] } }],
    loading: 'Loading triage progress',
    emptyCopy: 'No findings yet.',
    errorCopy: 'JAVV cannot show the triage progress.',
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

  it('Triage activity reads with its audit filters, and keeps its own entities (issue 1063)', async () => {
    fn('auditFacetsApiV1AuditFacetsGet').mockResolvedValue(ok({ activity: [] }))
    mountPanel(panelById('triage-activity')!, ctx({ auditFilters: { action: ['risk_accept'], exclude_actor: ['bot'] } }))
    await flushPromises()
    expect(fn('auditFacetsApiV1AuditFacetsGet').mock.calls[0]![0]).toMatchObject({
      query: {
        cluster_id: CLUSTER,
        entity_type: ['finding', 'decision'],
        action: ['risk_accept'],
        exclude_actor: ['bot'],
      },
    })
  })

  it('only Triage activity takes audit filters; it takes no findings filters', () => {
    expect(PANELS.filter((p) => p.takesAuditFilters).map((p) => p.id)).toEqual(['triage-activity'])
    expect(panelById('triage-activity')!.takesFilters).toBe(false)
  })

  it('the dashboard gives the stored audit filters only to a panel that takes them', () => {
    const audit = { action: ['resolve'] }
    // a stored panel that does not take them still carries them here: the dashboard is the guard
    const [triage, handled] = placePanels([
      { panel: 'triage-activity', x: 0, y: 0, w: 2, h: 'short', audit_filters: audit },
      { panel: 'handled-findings', x: 0, y: 1, w: 2, h: 'short', audit_filters: audit },
    ])
    const seen = vi.fn<NonNullable<typeof handled>['panel']['props']>(handled!.panel.props)
    const props = panelPropsCache()
    const dash = { clusterId: CLUSTER, t: null, windowDays: 30, scanner: 'all' as const }
    expect((props('0-0', triage!, dash).query as Record<string, unknown>).action).toEqual(['resolve'])
    props('0-1', { ...handled!, panel: { ...handled!.panel, props: seen } }, dash)
    expect(seen.mock.calls[0]![0].auditFilters).toBeNull()
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
    expect(w.text()).toContain('The leaderboard below is empty too.')
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
    expect(w.text()).toContain(`The ${rows} namespaces with the most findings.`)
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
    expect(w.text()).toContain('Nobody handled a finding in this range.')
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
    expect(w.text()).not.toContain('Nobody handled a finding in this range.')
    expect(w.find('[aria-label="Loading handled findings"]').exists()).toBe(true)
  })
})

describe('Riskiest images with no committed inventory', () => {
  it('says that no inventory is committed yet, not that the cluster has no findings', async () => {
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(ok({ inventory: null, images: [] }))
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    expect(w.text()).toContain('No inventory yet. JAVV shows the images when a scanner completes a scan cycle.')
    expect(w.text()).not.toContain('No image findings')
  })

  it('names the time of its answer, not a time whose read is still open', async () => {
    const timeTravel = (await import('@/stores/timeTravel')).useTimeTravelStore()
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValueOnce(ok({ inventory: null, images: [] })).mockReturnValueOnce(later())
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    timeTravel.rewindTo('2026-10-01T00:00:00.000Z')
    await flushPromises()
    expect(w.text()).toContain('No inventory yet.')
    expect(w.text()).not.toContain('at this point in time')
  })

  it('a committed inventory of the next cluster ends the no-inventory text', async () => {
    fn('listRunningImagesApiV1ImagesGet')
      .mockResolvedValueOnce(ok({ inventory: null, images: [] }))
      .mockResolvedValueOnce(ok({ inventory: INVENTORY, images: [] }))
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    expect(w.text()).toContain('No inventory yet.')
    useClusterStore().selectedId = 'c-other'
    await flushPromises()
    expect(w.text()).toContain('The running images have no findings.')
    expect(w.text()).not.toContain('No inventory committed')
  })

  it('a failed read after a no-inventory answer shows the error', async () => {
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValueOnce(ok({ inventory: null, images: [] })).mockResolvedValueOnce(refused())
    const w = mountPanel(panelById('riskiest-images')!)
    await flushPromises()
    useClusterStore().selectedId = 'c-other'
    await flushPromises()
    expect(w.text()).toContain('JAVV cannot show the riskiest images. Check the backend connection.')
    expect(w.text()).not.toContain('No inventory committed')
  })

  it('at a past time before the first inventory, says so for that time', async () => {
    const timeTravel = (await import('@/stores/timeTravel')).useTimeTravelStore()
    timeTravel.rewindTo('2026-10-01T00:00:00.000Z')
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(ok({ inventory: null, images: [] }))
    const w = mountPanel(panelById('riskiest-images')!, ctx({ t: '2026-10-01T00:00:00.000Z' }))
    await flushPromises()
    expect(w.text()).toContain('No inventory at this time.')
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

const ZERO = { crit: 0, high: 0, med: 0, low: 0, negligible: 0, unknown: 0 }
/** a row of the top-images read: the counts per scanner, no total (issue 1063) */
const TOP_IMAGE = {
  image_digest: 'sha256:top',
  image_repo: 'app/top',
  tag: '1.0',
  namespaces: ['payments'],
  severity_by_scanner: { trivy: { ...ZERO, crit: 2, high: 5 }, grype: { ...ZERO, crit: 1, high: 7 } },
}

describe('Riskiest images with filters (issue 1063)', () => {
  const FILTERS = { present: true, namespace: ['payments'], fixable: true }

  it('with no filters, reads the running images and not the ranked read', async () => {
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(ok({ inventory: INVENTORY, images: [] }))
    mountPanel(panelById('riskiest-images')!, ctx({ filters: null }))
    await flushPromises()
    expect(fn('listRunningImagesApiV1ImagesGet')).toHaveBeenCalledTimes(1)
    expect(fn('topImagesFindingsApiV1FindingsTopImagesGet')).not.toHaveBeenCalled()
  })

  it.each([
    ['all', undefined, '3', '12'],
    ['trivy', 'trivy', '2', '5'],
    ['grype', 'grype', '1', '7'],
  ] as const)('under %s, the store ranks for that scanner and the row shows its counts', async (scanner, sent, crit, high) => {
    fn('topImagesFindingsApiV1FindingsTopImagesGet').mockResolvedValue(ok({ inventory: INVENTORY, images: [TOP_IMAGE] }))
    const w = mountPanel(panelById('riskiest-images')!, ctx({ scanner, filters: FILTERS as never }))
    await flushPromises()
    expect(fn('listRunningImagesApiV1ImagesGet')).not.toHaveBeenCalled()
    const query = (fn('topImagesFindingsApiV1FindingsTopImagesGet').mock.calls[0]![0] as { query: Record<string, unknown> })
      .query
    expect(query).toMatchObject({ cluster_id: CLUSTER, namespace: ['payments'], fixable: true })
    expect(query.scanner).toBe(sent)
    expect(w.find('tbody tr td:nth-child(2)').text()).toBe(crit)
    expect(w.find('tbody tr td:nth-child(3)').text()).toBe(high)
  })

  it('a scanner switch reads again only when the panel has filters', async () => {
    fn('listRunningImagesApiV1ImagesGet').mockResolvedValue(ok({ inventory: INVENTORY, images: [] }))
    fn('topImagesFindingsApiV1FindingsTopImagesGet').mockResolvedValue(ok({ inventory: INVENTORY, images: [] }))
    const panel = panelById('riskiest-images')!
    const plain = mountPanel(panel)
    await flushPromises()
    await plain.setProps(panel.props(ctx({ scanner: 'trivy' })))
    await flushPromises()
    expect(fn('listRunningImagesApiV1ImagesGet')).toHaveBeenCalledTimes(1)

    const withFilters = mountPanel(panel, ctx({ filters: FILTERS as never }))
    await flushPromises()
    await withFilters.setProps(panel.props(ctx({ scanner: 'trivy', filters: FILTERS as never })))
    await flushPromises()
    expect(fn('topImagesFindingsApiV1FindingsTopImagesGet')).toHaveBeenCalledTimes(2)
  })

  it.each([
    ['trivy', 'grype', '2', '1'],
    ['all', 'grype', '3', '1'],
  ] as const)('a switch from %s to %s keeps the last answer until the next one comes', async (from, to, before, after) => {
    let land: (v: unknown) => void = () => {}
    fn('topImagesFindingsApiV1FindingsTopImagesGet')
      .mockResolvedValueOnce(ok({ inventory: INVENTORY, images: [TOP_IMAGE] }))
      .mockReturnValueOnce(new Promise((resolve) => (land = resolve)))
    const panel = panelById('riskiest-images')!
    const w = mountPanel(panel, ctx({ scanner: from, filters: FILTERS as never }))
    await flushPromises()
    await w.setProps(panel.props(ctx({ scanner: to, filters: FILTERS as never })))
    await flushPromises()
    // the counts of the answer on screen, as read, while the next read is open
    expect(w.find('tbody tr td:nth-child(2)').text()).toBe(before)
    land(ok({ inventory: INVENTORY, images: [TOP_IMAGE] }))
    await flushPromises()
    expect(w.find('tbody tr td:nth-child(2)').text()).toBe(after)
  })
})

describe('a panel with filters (issue 999)', () => {
  // a stored filters object, as the backend keeps it (`present: true` is the ViewPreset default).
  // The flag is on no row, so each link must carry a panel filter that its row does not set.
  const FILTERS = { present: true, exclude_namespace: ['kube-system'], kev: true }
  const filtered = ctx({ filters: FILTERS as never })

  /** each panel that takes filters, an answer that draws a row, and the element a click opens.
   * `calls` replaces the panel's reads when its filters change the route it reads; `opens` is the
   * page a row opens when it is not Findings. */
  const CASES: Record<
    string,
    {
      answers: unknown[]
      click: string
      row: Record<string, string>
      calls?: SdkName[]
      opens?: { path: string; query: Record<string, string> }
      /** the read takes no `all_filters`, and a click rewinds the time: no Findings link can
       * show the findings first seen in one bucket */
      rewinds?: true
    }
  > = {
    'findings-summary': { answers: [{ facets: FACETS }], click: '.stat-cell', row: { severity: 'critical' } },
    'package-type': { answers: [{ facets: FACETS }], click: '.donut-row', row: { ptype: 'debian' } },
    'findings-by-namespace': { answers: [{ facets: FACETS }], click: 'tbody tr', row: { namespace: 'ns-00' } },
    'top-components': {
      answers: [{ components: [{ package_name: 'openssl', count: 4, unique_cves_by_scanner: { trivy: 3 } }] }],
      click: 'tbody tr',
      row: { q: 'openssl' },
    },
    // issue 1176: the store ranks the CVEs under the filters; a row opens Findings on its CVE
    'top-cves': {
      answers: [
        {
          values: [
            {
              value: 'CVE-2024-0003',
              count: 3,
              count_by_scanner: { trivy: 3 },
              severity_by_scanner: { trivy: { high: 3 } },
            },
          ],
        },
      ],
      click: 'tbody tr',
      row: { cve: 'CVE-2024-0003' },
    },
    // issue 1292: the strip counts the new findings under the filters; a bar rewinds the time
    'new-findings': {
      answers: [{ series: { critical: [{ date: `${new Date().toISOString().slice(0, 10)}T00:00:00.000Z`, count: 2 }] } }],
      click: '',
      row: {},
      rewinds: true,
    },
    // issue 1063: with filters the store ranks the images; a row opens its image, as with none
    'riskiest-images': {
      answers: [{ inventory: INVENTORY, images: [TOP_IMAGE] }],
      click: 'tbody tr',
      row: {},
      calls: ['topImagesFindingsApiV1FindingsTopImagesGet'],
      opens: { path: '/images/sha256%3Atop', query: { repo: 'app/top', tag: '1.0' } },
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
    // Scan ingest counts scans, not findings: its own tests are below
    expect([...Object.keys(CASES), 'scan-ingest'].sort()).toEqual(PANELS.filter((p) => p.takesFilters).map((p) => p.id).sort())
  })

  it.each(Object.keys(CASES))('%s sends its filters, with all_filters, in each read', async (id) => {
    const c = CASES[id]!
    const calls = c.calls ?? READS[id]!.calls
    for (const name of new Set(calls)) {
      for (const a of c.answers) fn(name).mockResolvedValueOnce(ok(a))
    }
    mountFiltered(id)
    await flushPromises()
    const sent = calls.flatMap((name) => fn(name).mock.calls.map((call) => (call[0] as { query: object }).query))
    expect(sent.length).toBeGreaterThan(0)
    for (const q of sent) {
      expect(q).toMatchObject({ cluster_id: CLUSTER, exclude_namespace: ['kube-system'], kev: true })
      expect((q as { all_filters?: boolean }).all_filters).toBe(c.rewinds ? undefined : true)
    }
  })

  async function clickRow(id: string) {
    const c = CASES[id]!
    for (const name of new Set(c.calls ?? READS[id]!.calls)) {
      for (const a of c.answers) fn(name).mockResolvedValueOnce(ok(a))
    }
    const { w, router } = mountFiltered(id)
    await flushPromises()
    await w.find(c.click).trigger('click')
    await flushPromises()
    return router.currentRoute.value
  }

  it.each(Object.keys(CASES).filter((id) => !CASES[id]!.opens && !CASES[id]!.rewinds))(
    '%s opens Findings with its filters and the value of the row',
    async (id) => {
      const route = await clickRow(id)
      expect(route.query).toEqual({ namespace: '!kube-system', attr: 'kev', ...CASES[id]!.row })
    },
  )

  it.each(Object.keys(CASES).filter((id) => CASES[id]!.opens))('%s opens the page of its row', async (id) => {
    const route = await clickRow(id)
    expect({ path: route.path, query: route.query }).toEqual(CASES[id]!.opens)
  })

  it('new-findings rewinds the time to the end of the clicked day, as on the screens', async () => {
    fn('newFindingsTrendApiV1TrendsNewFindingsGet').mockResolvedValueOnce(ok(CASES['new-findings']!.answers[0]))
    const { w } = mountFiltered('new-findings')
    await flushPromises()
    const chart = w.findComponent({ name: 'EChart' })
    expect(chart.exists()).toBe(true)
    // 30 days give 31 daily bars, today last: bar 27 is the day of three days ago. The app
    // rewinds to the last millisecond of that UTC day.
    chart.vm.$emit('point-click', { dataIndex: 27 })
    await flushPromises()
    const today = new Date()
    const endOfThatDay = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - 2) - 1
    expect(useTimeTravelStore().t).toBe(new Date(endOfThatDay).toISOString())
  })

  it('new-findings sends the scanner of the panel, and no scanner for all scanners', async () => {
    fn('newFindingsTrendApiV1TrendsNewFindingsGet').mockResolvedValue(ok({ series: {} }))
    mountPanel(panelById('new-findings')!, ctx({ scanner: 'grype', filters: FILTERS as never }))
    mountPanel(panelById('new-findings')!, ctx({ scanner: 'all' }))
    await flushPromises()
    const [grype, all] = fn('newFindingsTrendApiV1TrendsNewFindingsGet').mock.calls.map(
      (call) => (call[0] as { query: Record<string, unknown> }).query,
    )
    expect(grype).toMatchObject({ scanner: 'grype', exclude_namespace: ['kube-system'], present: true })
    expect(all).not.toHaveProperty('scanner')
    expect(all).not.toHaveProperty('kev')
  })

  it('scan-ingest sends the scan filters of the panel, and no last-scan read (issue 1293)', async () => {
    fn('scansTrendApiV1TrendsScansGet').mockResolvedValue(ok({ series: {} }))
    fn('scannerFreshnessApiV1ScannersFreshnessGet').mockResolvedValue(ok({ scanners: [] }))
    const scan = { present: true, exclude_namespace: ['kube-system'], tag: ['1.2'], untagged: null }
    const w = mountPanel(panelById('scan-ingest')!, ctx({ filters: scan as never }))
    await flushPromises()
    const [q] = fn('scansTrendApiV1TrendsScansGet').mock.calls.map((call) => (call[0] as { query: object }).query)
    expect(q).toEqual({ cluster_id: CLUSTER, days: 30, interval: 'day', exclude_namespace: ['kube-system'], tag: ['1.2'] })
    expect(fn('scannerFreshnessApiV1ScannersFreshnessGet')).not.toHaveBeenCalled()
    // the settings offer only the scan filters, so the line about the other filters never shows
    expect(w.text()).not.toContain('Only the namespace')
  })

  it('scan-ingest sends the scanner of the panel, and no scanner for all scanners (Q1 A)', async () => {
    fn('scansTrendApiV1TrendsScansGet').mockResolvedValue(ok({ series: {} }))
    fn('scannerFreshnessApiV1ScannersFreshnessGet').mockResolvedValue(ok({ scanners: [] }))
    mountPanel(panelById('scan-ingest')!, ctx({ scanner: 'trivy', filters: null }))
    mountPanel(panelById('scan-ingest')!, ctx({ scanner: 'all', filters: null }))
    await flushPromises()
    const [trivy, all] = fn('scansTrendApiV1TrendsScansGet').mock.calls.map(
      (call) => (call[0] as { query: Record<string, unknown> }).query,
    )
    expect(trivy).toMatchObject({ scanner: 'trivy' })
    expect(all).not.toHaveProperty('scanner')
    // a scanner is a scan filter: the last scan of the whole cluster does not show (Q2 B of PR 2a)
    expect(fn('scannerFreshnessApiV1ScannersFreshnessGet')).toHaveBeenCalledTimes(1)
  })

  it('scan-ingest with no filters reads the whole cluster and the last scan, as before', async () => {
    fn('scansTrendApiV1TrendsScansGet').mockResolvedValue(ok({ series: {} }))
    fn('scannerFreshnessApiV1ScannersFreshnessGet').mockResolvedValue(ok({ scanners: [] }))
    mountPanel(panelById('scan-ingest')!, ctx({ filters: null }))
    await flushPromises()
    const [q] = fn('scansTrendApiV1TrendsScansGet').mock.calls.map((call) => (call[0] as { query: object }).query)
    expect(q).toEqual({ cluster_id: CLUSTER, days: 30, interval: 'day' })
    expect(fn('scannerFreshnessApiV1ScannersFreshnessGet')).toHaveBeenCalledTimes(1)
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
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }] })
    mount(panelById('findings-by-namespace')!.component, { props, global: { plugins: [router], stubs: { EChart: true } } })
    await flushPromises()
    expect((facetsMock().mock.calls[0]![0] as { query: object }).query).toMatchObject({ new_within_days: 30, all_filters: true })
  })
})

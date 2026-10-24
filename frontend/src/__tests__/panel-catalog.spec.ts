/**
 * The dashboard panel catalog (issue 440). Every panel in it must render on a page that gives it
 * nothing but a cluster and its settings (DESIGN.md §10): it sends its own request, and shows its
 * own loading, empty and error states. Here each panel mounts alone, with only that.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    topComponentsFindingsApiV1FindingsTopComponentsGet: vi.fn<() => Promise<unknown>>(),
    scansTrendApiV1TrendsScansGet: vi.fn<() => Promise<unknown>>(),
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
    ingestFailuresTrendApiV1TrendsIngestFailuresGet: vi.fn<() => Promise<unknown>>(),
    auditFacetsApiV1AuditFacetsGet: vi.fn<() => Promise<unknown>>(),
    facetFindingsApiV1FindingsFacetsGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import * as sdk from '@/api/generated'
import PanelFrame from '@/components/dashboards/PanelFrame.vue'
import {
  PANELS,
  TABLE_ROWS,
  globalQuery,
  heightsOf,
  panelById,
  type CatalogPanel,
  type PanelContext,
} from '@/dashboards/catalog'
import { useClusterStore } from '@/stores/cluster'

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

type SdkName = keyof typeof sdk
/** For each panel: the reads it sends, an empty answer for each, and the copy of each state. */
const READS: Record<
  string,
  { calls: SdkName[]; empty: unknown[]; loading: string; emptyCopy: string; errorCopy: string }
> = {
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

beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
  // the panels that read the app's cluster read the same one the dashboard passes
  useClusterStore().selectedId = CLUSTER
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
    for (const name of reads.calls) fn(name).mockReturnValue(new Promise(() => {}))
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
    expect(style).not.toMatch(/overflow\s*:/)
    expect(style).not.toMatch(/height\s*:\s*100%/)
  })

  it('frames only the panels that have no card of their own', () => {
    expect(PANELS.filter((p) => p.framed).map((p) => p.id)).toEqual(['triage-progress'])
  })
})

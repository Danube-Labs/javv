/**
 * One dashboard (issue 440, S7). The placement rules are pure (`dashboards/layout.ts`), so they
 * are tested as units: the reading order, the grid cell of each panel, the rows of a height
 * name, the scanner a pinned panel keeps. The view is mounted on a catalog of three stub panels
 * with the heights of the real catalog, so the test reads the props a panel gets, not the panel:
 * the cluster, T, the window and the scanner. A dashboard that the server does not give (404,
 * decision Q3) is the "not found" page.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

/** a stub panel: its props, and how many times it rendered (a new prop object renders it again) */
const Probe = defineComponent({
  props: ['scanner', 'query', 'clusterId', 't', 'windowDays', 'pageSize'],
  setup(props) {
    let renders = 0
    return () => h('div', { class: 'probe', 'data-props': JSON.stringify(props), 'data-renders': String(++renders) })
  },
})

vi.mock('@/dashboards/catalog', () => ({
  panelById: (id: string) =>
    ({
      'findings-summary': {
        id: 'findings-summary',
        name: 'Findings summary',
        line: 'one line',
        component: Probe,
        heights: { short: 7 },
        usesScanner: true,
        framed: false,
        props: (ctx: { clusterId: string; t: string | null; scanner: string; windowDays: number }) => ({
          scanner: ctx.scanner,
          query: { cluster_id: ctx.clusterId, ...(ctx.t ? { as_of: ctx.t } : {}) },
          windowDays: ctx.windowDays,
        }),
      },
      'top-components': {
        id: 'top-components',
        name: 'Top components',
        line: 'one line',
        component: Probe,
        heights: { short: 13, tall: 26 },
        usesScanner: true,
        framed: false,
        props: (ctx: { scanner: string; height: string }) => ({
          scanner: ctx.scanner,
          pageSize: ctx.height === 'tall' ? 20 : 10,
        }),
      },
      'triage-progress': {
        id: 'triage-progress',
        name: 'Triage progress',
        line: 'For each severity, how many findings people have triaged.',
        component: Probe,
        heights: { short: 10 },
        usesScanner: false,
        framed: true,
        props: (ctx: { clusterId: string }) => ({ query: { cluster_id: ctx.clusterId } }),
      },
    })[id],
}))
vi.mock('@/api/generated', () => ({
  getDashboardApiV1DashboardsDashboardIdGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import type { DashboardPanel } from '@/api/generated'
import { getDashboardApiV1DashboardsDashboardIdGet } from '@/api/generated'
import { cellStyle, changedLine, isPinned, panelScanner, placePanels, sharingLine } from '@/dashboards/layout'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import DashboardView from '@/views/DashboardView.vue'

const ID = 'a'.repeat(32)
const PANELS: DashboardPanel[] = [
  { panel: 'top-components', x: 1, y: 7, w: 1, h: 'tall' },
  { panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short' },
  { panel: 'findings-summary', x: 0, y: 7, w: 1, h: 'short', scanner: 'grype' },
  { panel: 'triage-progress', x: 0, y: 14, w: 1, h: 'short' },
]
const DOC = {
  dashboard_id: ID,
  name: 'Weekly risk review',
  description: 'What the security leads look at on Monday.',
  owner: 'lead',
  scanner: 'trivy',
  panels: PANELS,
  sharing: 'everyone',
  roles: [],
  updated_at: new Date().toISOString(),
  updated_by: 'lead',
}

const answer = (status: number, data?: unknown) =>
  ({ data, request: {}, response: { ok: status < 300, status } }) as never

async function mountView(query = '', id = ID) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboards/:id', component: DashboardView },
      { path: '/:any(.*)*', name: 'overview', component: { template: '<div />' } },
    ],
  })
  await router.push(`/dashboards/${id}${query}`)
  const w = mount(DashboardView, { global: { plugins: [router, [PrimeVue, { unstyled: true }]] } })
  await flushPromises()
  return { w, router }
}

function probeProps(w: ReturnType<typeof mount>) {
  return w.findAll('.dash-cell').map((c) => ({
    panel: c.attributes('data-panel'),
    props: JSON.parse(c.find('.probe').attributes('data-props')!),
  }))
}

function renders(w: ReturnType<typeof mount>) {
  return w.findAll('.probe').map((p) => Number(p.attributes('data-renders')))
}

/** the heights and the scanner data of each panel in catalog.py, which a spec keeps equal to the
 * frontend catalog */
function backendCatalog(): Map<string, { heights: Record<string, number>; usesScanner: boolean }> {
  const text = readFileSync(resolve(process.cwd(), '..', 'backend/src/backend/dashboards/catalog.py'), 'utf8')
  const panels = new Map<string, { heights: Record<string, number>; usesScanner: boolean }>()
  for (const m of text.matchAll(/^\s+"([\w-]+)": CatalogPanel\(\{([^}]*)\}, uses_scanner=(True|False)\),$/gm)) {
    const heights: Record<string, number> = {}
    for (const hm of m[2]!.matchAll(/"(\w+)": (\d+)/g)) heights[hm[1]!] = Number(hm[2])
    panels.set(m[1]!, { heights, usesScanner: m[3] === 'True' })
  }
  return panels
}

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.clusters = [{ cluster_id: 'c-1', cluster_name: 'alpha' }] as never
  clusters.selectedId = 'c-1'
  vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(200, DOC))
})
afterEach(() => vi.clearAllMocks())

describe('layout', () => {
  it('the stub panels have the heights and the scanner data of the real catalog', () => {
    const real = backendCatalog()
    for (const id of ['findings-summary', 'top-components', 'triage-progress']) {
      const stub = placePanels([{ panel: id as never, x: 0, y: 0, w: 1, h: 'short' }])[0]!.panel
      expect({ heights: stub.heights, usesScanner: stub.usesScanner }).toEqual(real.get(id))
    }
  })

  it('reads the panels in order y, then x, and leaves out a panel the catalog does not list', () => {
    const placed = placePanels([...PANELS, { panel: 'gone' as never, x: 0, y: 40, w: 1, h: 'short' }])
    expect(placed.map((p) => [p.stored.x, p.stored.y])).toEqual([
      [0, 0],
      [0, 7],
      [1, 7],
      [0, 14],
    ])
  })

  it('takes the rows from the catalog height that the panel names', () => {
    const [summary, , top] = placePanels(PANELS)
    expect(summary!.rows).toBe(7)
    expect(top!.rows).toBe(26)
    expect(cellStyle(top!)).toEqual({ '--col': '2', '--cols': '1', '--row': '8', '--rows': '26' })
  })

  it('uses the first catalog height for a height the panel cannot take', () => {
    const [p] = placePanels([{ panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'tall' }])
    expect(p!.rows).toBe(7)
  })

  it('a pinned panel keeps its scanner; any other follows the switch (Q7)', () => {
    expect(panelScanner(PANELS[2]!, 'all')).toBe('grype')
    expect(isPinned(PANELS[2]!)).toBe(true)
    expect(panelScanner(PANELS[1]!, 'trivy')).toBe('trivy')
    expect(panelScanner({ ...PANELS[1]!, scanner: 'dashboard' }, 'all')).toBe('all')
    expect(isPinned({ ...PANELS[1]!, scanner: 'dashboard' })).toBe(false)
  })

  it('names who can see it, and when it changed', () => {
    expect(sharingLine('everyone', [])).toBe('Everyone')
    expect(sharingLine('roles', ['security_lead', 'triager'])).toBe('security_lead, triager')
    expect(sharingLine('private', [])).toBe('Only the owner')
    const now = Date.parse('2026-10-25T12:00:00Z')
    expect(changedLine('2026-10-25T09:30:00Z', 'lead', now)).toBe('changed 2 hours ago by lead')
    expect(changedLine(undefined, 'lead', now)).toBe('')
  })
})

describe('the read page', () => {
  it('draws each panel with the cluster and the scanner the owner saved', async () => {
    const { w } = await mountView()
    expect(w.find('h1').text()).toBe('Weekly risk review')
    expect(w.find('.dash-meta').text()).toContain('Everyone')
    expect(w.find('.dash-meta').text()).toContain('alpha')
    expect(probeProps(w)).toEqual([
      { panel: 'findings-summary', props: { scanner: 'trivy', query: { cluster_id: 'c-1' }, windowDays: 30 } },
      { panel: 'findings-summary', props: { scanner: 'grype', query: { cluster_id: 'c-1' }, windowDays: 30 } },
      { panel: 'top-components', props: { scanner: 'trivy', pageSize: 20 } },
      { panel: 'triage-progress', props: { query: { cluster_id: 'c-1' } } },
    ])
  })

  it('follows the scanner in the URL, and keeps that choice in the URL', async () => {
    const { w, router } = await mountView('?scanner=all&t=x')
    expect(probeProps(w).map((p) => p.props.scanner)).toEqual(['all', 'grype', 'all', undefined])
    const grype = w.findAll('.head-actions button').find((b) => b.text() === 'grype')!
    await grype.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ scanner: 'grype', t: 'x' })
    expect(probeProps(w).map((p) => p.props.scanner)).toEqual(['grype', 'grype', 'grype', undefined])
  })

  it('the switch renders again only the panels that follow it', async () => {
    const { w } = await mountView('?scanner=all')
    expect(renders(w)).toEqual([1, 1, 1, 1])
    await w.findAll('.head-actions button').find((b) => b.text() === 'trivy')!.trigger('click')
    await flushPromises()
    // the pinned grype panel and the panel with no scanner data keep their props
    expect(renders(w)).toEqual([2, 1, 2, 1])
  })

  it('shows the pin on a pinned panel only, and frames a panel with no card', async () => {
    const { w } = await mountView()
    const cells = w.findAll('.dash-cell')
    expect(cells.map((c) => c.find('.dash-pin').exists())).toEqual([false, true, false, false])
    expect(cells[1]!.find('.dash-pin').text()).toBe('grype pinned')
    expect(cells[3]!.find('.panel-frame h2').text()).toBe('Triage progress')
  })

  it('gives each panel the T of the time picker', async () => {
    useTimeTravelStore().t = '2026-10-01T00:00:00Z'
    const { w } = await mountView()
    expect(probeProps(w)[0]!.props.query).toEqual({ cluster_id: 'c-1', as_of: '2026-10-01T00:00:00Z' })
  })

  it('a dashboard the server does not give is the "not found" page (Q3)', async () => {
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(404))
    const { w } = await mountView()
    expect(w.text()).toContain('Page not found')
    expect(w.find('.dash-grid').exists()).toBe(false)
  })

  it('while it loads, the head card is on the page, so it can stretch when the name arrives', async () => {
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockImplementationOnce(() => new Promise(() => {}) as never)
    const { w } = await mountView()
    expect(w.find('.head-card h1').text()).toBe('Dashboard')
    expect(w.find('[aria-label="Loading the dashboard"]').exists()).toBe(true)
    expect(w.find('.head-actions').exists()).toBe(false)
  })

  it('a late answer for a dashboard the user left does not replace the one on the page', async () => {
    const OTHER = 'b'.repeat(32)
    let answerFirst: (v: unknown) => void = () => {}
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockImplementation((opts) => {
      const id = (opts as { path: { dashboard_id: string } }).path.dashboard_id
      if (id === ID) return new Promise((done) => (answerFirst = done)) as never
      return Promise.resolve(answer(200, { ...DOC, dashboard_id: OTHER, name: 'Second' }))
    })
    const { w, router } = await mountView()
    await router.push(`/dashboards/${OTHER}`)
    await flushPromises()
    expect(w.find('h1').text()).toBe('Second')
    answerFirst(answer(200, DOC))
    await flushPromises()
    expect(w.find('h1').text()).toBe('Second')
  })

  it('an OK answer with no body it can read says the dashboard is unavailable', async () => {
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(200))
    const { w } = await mountView()
    expect(w.find('.load-error').text()).toContain('The dashboard is unavailable')
  })

  it('a refused read says why', async () => {
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(429))
    const { w } = await mountView()
    expect(w.find('.load-error').text()).toBe('The search backend is busy. Try again in a few seconds.')
  })

  it('with no cluster, and with no panels, it says so', async () => {
    useClusterStore().selectedId = null as never
    const { w } = await mountView()
    expect(w.text()).toContain('No cluster to show')
    useClusterStore().selectedId = 'c-1'
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(200, { ...DOC, panels: [] }))
    const again = await mountView()
    expect(again.w.text()).toContain('This dashboard has no panels')
  })
})

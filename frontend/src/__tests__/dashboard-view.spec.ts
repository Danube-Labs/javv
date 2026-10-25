/**
 * One dashboard (issue 440, S7). The placement rules are pure (`dashboards/layout.ts`), so they
 * are tested as units: the reading order, the grid cell of each panel, the rows of a height
 * name, the scanner a pinned panel keeps. The view is mounted on a catalog of two stub panels,
 * so the test reads the props a panel gets, not the panel: the cluster, T, the window and the
 * scanner. A dashboard that the server does not give (404, ruling Q3) is the "not found" page.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

const Probe = defineComponent({
  props: ['scanner', 'query', 'clusterId', 't', 'windowDays', 'rows'],
  setup(props) {
    return () => h('div', { class: 'probe', 'data-props': JSON.stringify(props) })
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
      'triage-progress': {
        id: 'triage-progress',
        name: 'Triage progress',
        line: 'For each severity, how many findings people have triaged.',
        component: Probe,
        heights: { short: 10, tall: 20 },
        usesScanner: false,
        framed: true,
        props: (ctx: { clusterId: string }) => ({ clusterId: ctx.clusterId }),
      },
    })[id],
}))
vi.mock('@/api/generated', () => ({ getDashboardApiV1DashboardsDashboardIdGet: vi.fn() }))
vi.mock('@/api/client', () => ({ client: {} }))

import type { DashboardPanel } from '@/api/generated'
import { getDashboardApiV1DashboardsDashboardIdGet } from '@/api/generated'
import { cellStyle, changedLine, isPinned, panelScanner, placePanels, sharingLine } from '@/dashboards/layout'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import DashboardView from '@/views/DashboardView.vue'

const ID = 'a'.repeat(32)
const PANELS: DashboardPanel[] = [
  { panel: 'triage-progress', x: 1, y: 7, w: 1, h: 'tall' },
  { panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short' },
  { panel: 'findings-summary', x: 0, y: 7, w: 1, h: 'short', scanner: 'grype' },
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

async function mountView(query = '') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboards/:id', component: DashboardView },
      { path: '/:any(.*)*', name: 'overview', component: { template: '<div />' } },
    ],
  })
  await router.push(`/dashboards/${ID}${query}`)
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

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.clusters = [{ cluster_id: 'c-1', cluster_name: 'alpha' }] as never
  clusters.selectedId = 'c-1'
  vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(200, DOC))
})
afterEach(() => vi.clearAllMocks())

describe('layout', () => {
  it('reads the panels in order y, then x, and leaves out a panel the catalog does not list', () => {
    const placed = placePanels([...PANELS, { panel: 'gone' as never, x: 0, y: 30, w: 1, h: 'short' }])
    expect(placed.map((p) => [p.stored.x, p.stored.y])).toEqual([
      [0, 0],
      [0, 7],
      [1, 7],
    ])
  })

  it('takes the rows from the catalog height that the panel names', () => {
    const [summary, , progress] = placePanels(PANELS)
    expect(summary!.rows).toBe(7)
    expect(progress!.rows).toBe(20)
    expect(cellStyle(progress!)).toEqual({ '--col': '2', '--cols': '1', '--row': '8', '--rows': '20' })
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
      { panel: 'triage-progress', props: { clusterId: 'c-1' } },
    ])
  })

  it('follows the scanner in the URL, and keeps that choice in the URL', async () => {
    const { w, router } = await mountView('?scanner=all&t=x')
    expect(probeProps(w).map((p) => p.props.scanner)).toEqual(['all', 'grype', undefined])
    const grype = w.findAll('.head-actions button').find((b) => b.text() === 'grype')!
    await grype.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ scanner: 'grype', t: 'x' })
    expect(probeProps(w).map((p) => p.props.scanner)).toEqual(['grype', 'grype', undefined])
  })

  it('shows the pin on a pinned panel only, and frames a panel with no card', async () => {
    const { w } = await mountView()
    const cells = w.findAll('.dash-cell')
    expect(cells.map((c) => c.find('.dash-pin').exists())).toEqual([false, true, false])
    expect(cells[1]!.find('.dash-pin').text()).toBe('grype pinned')
    expect(cells[2]!.find('.panel-frame h2').text()).toBe('Triage progress')
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

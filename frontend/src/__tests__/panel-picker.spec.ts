/**
 * The catalog window of edit mode (issue 440, S8b, rulings Q1 and Q2). The dialog is mounted on
 * a catalog of four stub panels, so a test reads the props its preview gets: the cluster, the
 * scanner of the choice and the rows of the height. The view tests add a panel the way a user
 * does and read what the page then asks gridstack and the backend to do, with the fake gridstack
 * of `helpers/fakeGridstack.ts`.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('gridstack', () => import('./helpers/fakeGridstack'))

const Probe = defineComponent({
  props: ['scanner', 'pageSize', 'clusterId'],
  setup: (props) => () => h('div', { class: 'probe', 'data-props': JSON.stringify(props) }),
})
vi.mock('@/dashboards/catalog', () => {
  // built on first use: the stub component is not defined yet when this factory runs
  const panels = () => [
    {
      id: 'findings-summary',
      name: 'Findings summary',
      group: 'Findings',
      line: 'Findings in each severity.',
      component: Probe,
      defaultWidth: 2,
      heights: { short: 7 },
      usesScanner: true,
      framed: false,
      props: (ctx: { scanner: string; clusterId: string }) => ({ scanner: ctx.scanner, clusterId: ctx.clusterId }),
    },
    {
      id: 'top-components',
      name: 'Top components',
      group: 'Findings',
      line: 'The packages with the most vulnerabilities.',
      component: Probe,
      defaultWidth: 1,
      heights: { short: 13, tall: 26 },
      usesScanner: true,
      framed: false,
      props: (ctx: { scanner: string; height: string }) => ({
        scanner: ctx.scanner,
        pageSize: ctx.height === 'tall' ? 25 : 10,
      }),
    },
    {
      id: 'scan-ingest',
      name: 'Scan ingest',
      group: 'Scanners',
      line: 'Scan runs that reached JAVV.',
      component: Probe,
      defaultWidth: 2,
      heights: { short: 4 },
      usesScanner: false,
      framed: false,
      props: (ctx: { clusterId: string }) => ({ clusterId: ctx.clusterId }),
    },
    {
      id: 'triage-progress',
      name: 'Triage progress',
      group: 'People',
      line: 'For each severity, how many findings people have triaged.',
      component: Probe,
      defaultWidth: 1,
      heights: { short: 10 },
      usesScanner: false,
      framed: true,
      props: () => ({}),
    },
  ]
  let cached: ReturnType<typeof panels> | null = null
  const all = () => (cached ??= panels())
  return {
    get PANELS() {
      return all()
    },
    panelById: (id: string) => all().find((p) => p.id === id),
    heightsOf: (p: { heights: Record<string, number> }) => Object.keys(p.heights),
  }
})
vi.mock('@/api/generated', () => ({
  getDashboardApiV1DashboardsDashboardIdGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  updateDashboardApiV1DashboardsDashboardIdPatch: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import type { DashboardPanel } from '@/api/generated'
import {
  getDashboardApiV1DashboardsDashboardIdGet,
  updateDashboardApiV1DashboardsDashboardIdPatch,
} from '@/api/generated'
import AddPanelDialog from '@/components/dashboards/AddPanelDialog.vue'
import UiRoleNote from '@/components/ui/UiRoleNote.vue'
import { addedPanel, MAX_PANELS, PANEL_CAP_NOTE, type DraftPanel } from '@/dashboards/edit'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import DashboardView from '@/views/DashboardView.vue'

import { gs, resetGridstack } from './helpers/fakeGridstack'

const ID = 'c'.repeat(32)
const answer = (status: number, data?: unknown) =>
  ({ data, request: {}, response: { ok: status < 300, status } }) as never
const button = (w: { findAll: (s: string) => { text: () => string }[] }, text: string) =>
  w.findAll('button').find((b) => b.text() === text) as ReturnType<ReturnType<typeof mount>['find']>
const probeProps = (w: ReturnType<typeof mount>) => JSON.parse(w.find('.cat-prev .probe').attributes('data-props')!)

describe('the place of a new panel', () => {
  const draft: DraftPanel[] = [
    { key: 'a', panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short' },
    { key: 'b', panel: 'top-components', x: 1, y: 7, w: 1, h: 'tall' },
    { key: 'c', panel: 'triage-progress', x: 0, y: 7, w: 1, h: 'short' },
  ]
  it('goes to the left edge, under the lowest panel', () => {
    // top components ends at 7 + 26, under triage progress at 7 + 10
    expect(addedPanel(draft, { panel: 'scan-ingest', w: 2, h: 'short', scanner: null })).toMatchObject({
      x: 0,
      y: 33,
      w: 2,
    })
    expect(addedPanel([], { panel: 'scan-ingest', w: 1, h: 'short', scanner: null })).toMatchObject({ x: 0, y: 0 })
  })
  it('keeps a scanner only for a panel with scanner data, and gets a new key each time', () => {
    const a = addedPanel(draft, { panel: 'top-components', w: 1, h: 'tall', scanner: 'trivy' })
    const b = addedPanel(draft, { panel: 'scan-ingest', w: 1, h: 'short', scanner: null })
    expect(a.scanner).toBe('trivy')
    expect('scanner' in b).toBe(false)
    expect(a.key).not.toBe(b.key)
  })
})

describe('the catalog window', () => {
  const mountDialog = (over: Record<string, unknown> = {}) =>
    mount(AddPanelDialog, {
      props: { count: 3, clusterId: 'c1', t: null, windowDays: 30, dashboardScanner: 'trivy', ...over },
      global: { plugins: [[PrimeVue, { unstyled: true }]] },
    })

  it('lists every panel under its group, with its line, and says how many the dashboard has', () => {
    const w = mountDialog()
    expect(w.findAll('.cat-group').map((g) => g.text())).toEqual(['Findings', 'Scanners', 'People'])
    expect(w.findAll('.cat-row').map((r) => r.attributes('data-panel'))).toEqual([
      'findings-summary',
      'top-components',
      'scan-ingest',
      'triage-progress',
    ])
    expect(w.find('[data-panel="scan-ingest"] .cat-line').text()).toBe('Scan runs that reached JAVV.')
    expect(w.text()).toContain(`This dashboard has 3 of ${MAX_PANELS}.`)
  })

  it('the first panel is chosen, at its default width, and the preview reads live data', () => {
    const w = mountDialog()
    expect(w.find('.cat-row-on').attributes('data-panel')).toBe('findings-summary')
    expect(w.find('.cat-prev').classes()).not.toContain('cat-prev-half')
    // 7 rows of 40 px, less the grid margin: the slot it gets on the dashboard
    expect(w.find('.cat-prev').attributes('style')).toContain('height: 250px')
    expect(probeProps(w)).toEqual({ scanner: 'trivy', clusterId: 'c1' })
  })

  it('a panel shows only the settings it has, and a new choice starts from its defaults', async () => {
    const w = mountDialog()
    const labels = () => w.findAll('.ui-fld-label').map((l) => l.text())
    await w.find('[data-panel="top-components"]').trigger('click')
    expect(labels()).toEqual(['Scanner', 'Width', 'Height'])
    expect(w.find('.cat-prev').classes()).toContain('cat-prev-half')
    await button(w, 'Tall').trigger('click')
    await button(w, 'grype').trigger('click')
    expect(probeProps(w)).toEqual({ scanner: 'grype', pageSize: 25 })
    expect(w.find('.cat-help').text()).toContain('always shows grype')
    expect(w.find('.cat-prev').attributes('style')).toContain(`height: ${26 * 40 - 30}px`)

    await w.find('[data-panel="scan-ingest"]').trigger('click')
    expect(labels()).toEqual(['Width'])
    await w.find('[data-panel="top-components"]').trigger('click')
    expect(probeProps(w)).toEqual({ scanner: 'trivy', pageSize: 10 })
  })

  it('a panel with no card of its own gets the panel frame in the preview', async () => {
    const w = mountDialog()
    await w.find('[data-panel="triage-progress"]').trigger('click')
    expect(w.find('.cat-prev .panel-frame h2').text()).toBe('Triage progress')
  })

  it('Add panel sends the choice; Cancel sends nothing', async () => {
    const w = mountDialog()
    await w.find('[data-panel="top-components"]').trigger('click')
    await button(w, 'Full').trigger('click')
    await button(w, 'Add panel').trigger('click')
    expect(w.emitted('add')).toEqual([[{ panel: 'top-components', w: 2, h: 'short', scanner: 'dashboard' }]])
    await w.find('[data-panel="scan-ingest"]').trigger('click')
    await button(w, 'Add panel').trigger('click')
    expect(w.emitted('add')![1]).toEqual([{ panel: 'scan-ingest', w: 2, h: 'short', scanner: null }])
    await button(w, 'Cancel').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
    expect(w.emitted('add')).toHaveLength(2)
  })

  it('with no cluster, the preview reads nothing and says why', () => {
    const w = mountDialog({ clusterId: null })
    expect(w.find('.cat-prev').exists()).toBe(false)
    expect(w.text()).toContain('Select a cluster at the top of the page to see the preview.')
  })
})

describe('Add panel in edit mode', () => {
  const PANELS: DashboardPanel[] = [
    { panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short', scanner: 'dashboard' },
    { panel: 'top-components', x: 0, y: 7, w: 1, h: 'short', scanner: 'dashboard' },
  ]
  const doc = (panels: DashboardPanel[]) => ({
    dashboard_id: ID,
    name: 'Weekly risk review',
    description: '',
    owner: 'lead',
    scanner: 'all',
    panels,
    sharing: 'private',
    roles: [],
    updated_at: new Date().toISOString(),
    updated_by: 'lead',
    revision: 2,
  })

  beforeEach(() => {
    setActivePinia(createPinia())
    useClusterStore().selectedId = 'c1'
    useAuthStore().user = { username: 'lead', role: 'x', capabilities: ['can_edit_dashboards'], must_change: false }
    resetGridstack()
    vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mockImplementation(async (opts) =>
      answer(200, doc((opts as { body: { panels: DashboardPanel[] } }).body.panels)),
    )
  })
  afterEach(() => vi.clearAllMocks())

  async function mountView(panels: DashboardPanel[]) {
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(200, doc(panels)))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/dashboards/:id', component: DashboardView }],
    })
    await router.push(`/dashboards/${ID}?edit=1`)
    const w = mount(DashboardView, { global: { plugins: [router, [PrimeVue, { unstyled: true }]] } })
    await vi.dynamicImportSettled()
    await flushPromises()
    return w
  }
  const patchedPanels = () =>
    (vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mock.calls.at(-1)![0] as { body: { panels: DashboardPanel[] } })
      .body.panels

  it('a panel from the window goes under the others, into gridstack and into the save', async () => {
    const w = await mountView(PANELS)
    await button(w, 'Add panel').trigger('click')
    await flushPromises()
    const dialog = w.find('[role="dialog"]')
    await dialog.find('[data-panel="scan-ingest"]').trigger('click')
    await button(dialog, 'Add panel').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    const added = w.find('.grid-stack-item[data-panel="scan-ingest"]')
    expect([added.attributes('gs-x'), added.attributes('gs-y')]).toEqual(['0', '20'])
    expect(gs.made).toEqual([added.attributes('gs-id')])
    expect(w.find('.save-msg').text()).toBe('You have unsaved changes')

    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchedPanels()).toContainEqual({ panel: 'scan-ingest', x: 0, y: 20, w: 2, h: 'short' })
    expect(patchedPanels()).toHaveLength(3)
  })

  it('a new panel is saved where top mode puts it, not where it was added', async () => {
    // a half panel under a short half panel: gridstack packs it up next to the taller one
    gs.pack = (node) => ({ ...node, y: 7 })
    const w = await mountView(PANELS)
    await button(w, 'Add panel').trigger('click')
    await flushPromises()
    const dialog = w.find('[role="dialog"]')
    await dialog.find('[data-panel="top-components"]').trigger('click')
    await button(dialog, 'Add panel').trigger('click')
    await flushPromises()
    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchedPanels().filter((p) => p.panel === 'top-components').map((p) => [p.x, p.y])).toEqual([
      [0, 7],
      [0, 7],
    ])
  })

  it(`at ${MAX_PANELS} panels Add panel is off, with the reason next to it`, async () => {
    const full = Array.from({ length: MAX_PANELS }, (_, i) => ({
      panel: 'scan-ingest' as const,
      x: 0,
      y: i * 4,
      w: 2 as const,
      h: 'short' as const,
    }))
    const w = await mountView(full)
    const add = button(w, 'Add panel')
    expect(add.attributes('disabled')).toBeDefined()
    expect(add.attributes('aria-describedby')).toBe('panel-cap-note')
    expect(w.find('#panel-cap-note').text()).toBe(PANEL_CAP_NOTE)
    // the limit is not a permission, so its note has no key
    const keyIcon = mount(UiRoleNote, { props: { id: 'k' } }).find('path').attributes('d')
    expect(w.find('#panel-cap-note path').attributes('d')).not.toBe(keyIcon)

    // one panel less and it is on again
    await w.find('[aria-label="Remove Scan ingest"]').trigger('click')
    await flushPromises()
    expect(button(w, 'Add panel').attributes('disabled')).toBeUndefined()
    expect(w.find('#panel-cap-note').exists()).toBe(false)
  })

  it('a dashboard with no panels offers Add panel, and its first panel is a change to save', async () => {
    const w = await mountView([])
    expect(w.find('.grid-stack').exists()).toBe(false)
    const empty = w.findComponent({ name: 'EmptyState' })
    expect(empty.text()).toContain('This dashboard has no panels')
    await empty.findAll('button').find((b) => b.text() === 'Add panel')!.trigger('click')
    await flushPromises()
    await button(w.find('[role="dialog"]'), 'Add panel').trigger('click')
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(w.findAll('.grid-stack-item').map((i) => i.attributes('data-panel'))).toEqual(['findings-summary'])
    expect(w.find('.save-msg').text()).toBe('You have unsaved changes')
    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchedPanels()).toEqual([{ panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short', scanner: 'dashboard' }])
  })
})

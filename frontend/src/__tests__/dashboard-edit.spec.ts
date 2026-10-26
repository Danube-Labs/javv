/**
 * Edit mode of a dashboard (issue 440, S8a). The rules in `dashboards/edit.ts` are pure, so they
 * are tested as units: who may change a dashboard (D3), when two layouts are the same, what a
 * panel's settings do to its place, and what a refused save says. The view is mounted with the
 * fake gridstack of `helpers/fakeGridstack.ts`, so a test can move a panel the way a drop does
 * and read what the page then asks gridstack and the backend to do.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('gridstack', () => import('./helpers/fakeGridstack'))

const Probe = defineComponent({
  props: ['scanner', 'pageSize'],
  setup: (props) => () => h('div', { class: 'probe', 'data-props': JSON.stringify(props) }),
})
vi.mock('@/dashboards/catalog', () => {
  // built on first use: the stub component is not defined yet when this factory runs
  const panels = (): Record<string, unknown> => ({
    'findings-summary': {
      id: 'findings-summary',
      name: 'Findings summary',
      line: 'one line',
      component: Probe,
      heights: { short: 7 },
      usesScanner: true,
      framed: false,
      props: (ctx: { scanner: string }) => ({ scanner: ctx.scanner }),
    },
    'top-components': {
      id: 'top-components',
      name: 'Top components',
      line: 'The packages with the most vulnerabilities.',
      component: Probe,
      heights: { short: 13, tall: 26 },
      usesScanner: true,
      framed: false,
      props: (ctx: { scanner: string; height: string }) => ({
        scanner: ctx.scanner,
        pageSize: ctx.height === 'tall' ? 25 : 10,
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
      props: () => ({}),
    },
  })
  return {
    panelById: (id: string) => panels()[id],
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
import {
  editRefusal,
  NO_EDIT_NOTE,
  NO_EDIT_ROLE_NOTE,
  sameLayout,
  saveFailureCopy,
  withPlaces,
  withSettings,
  type DraftPanel,
} from '@/dashboards/edit'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'
import DashboardView from '@/views/DashboardView.vue'

import { gs, resetGridstack } from './helpers/fakeGridstack'

const ID = 'b'.repeat(32)
const PANELS: DashboardPanel[] = [
  { panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short', scanner: 'dashboard' },
  { panel: 'top-components', x: 0, y: 7, w: 1, h: 'short', scanner: 'dashboard' },
  { panel: 'triage-progress', x: 1, y: 7, w: 1, h: 'short' },
]
const doc = (over: Record<string, unknown> = {}) => ({
  dashboard_id: ID,
  name: 'Weekly risk review',
  description: '',
  owner: 'lead',
  scanner: 'all',
  panels: PANELS,
  sharing: 'everyone',
  roles: [],
  updated_at: new Date().toISOString(),
  updated_by: 'lead',
  revision: 4,
  ...over,
})
const answer = (status: number, data?: unknown, error?: unknown) =>
  ({ data, error, request: {}, response: { ok: status < 300, status } }) as never

function signIn(username: string, capabilities: string[]) {
  useAuthStore().user = { username, role: 'x', capabilities, must_change: false }
}

async function settle() {
  await vi.dynamicImportSettled()
  await flushPromises()
}

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
  await settle()
  return { w, router }
}

/** a drop: gridstack moved these panels and tells the page */
async function drop(moves: Record<string, { x: number; y: number }>) {
  const moved = gs.nodes.filter((n) => moves[n.el.getAttribute('data-panel')!])
  for (const n of moved) Object.assign(n, moves[n.el.getAttribute('data-panel')!])
  gs.onChange!({}, moved)
  await flushPromises()
}

const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find((b) => b.text() === text)!
const patchBody = () => vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mock.calls.at(-1)![0] as never as {
  body: { revision: number; panels?: DashboardPanel[] }
}

describe('who may change a dashboard (D3)', () => {
  const can = (caps: string[]) => (c: string) => caps.includes('*') || caps.includes(c)
  it('needs can_edit_dashboards, and another user dashboard also needs can_manage_settings', () => {
    expect(editRefusal('lead', can(['can_edit_dashboards']), 'lead')).toBeNull()
    expect(editRefusal('ana', can(['can_edit_dashboards']), 'lead')).toBe(NO_EDIT_NOTE)
    expect(editRefusal('ana', can(['can_edit_dashboards', 'can_manage_settings']), 'lead')).toBeNull()
    expect(editRefusal('admin', can(['*']), 'lead')).toBeNull()
    // an owner whose role lost the capability cannot change their own dashboard either
    expect(editRefusal('lead', can([]), 'lead')).toBe(NO_EDIT_ROLE_NOTE)
    expect(editRefusal(undefined, can([]), 'lead')).toBe(NO_EDIT_ROLE_NOTE)
  })
})

describe('the edit rules', () => {
  it('two layouts are the same in any order, and differ on any field of any panel', () => {
    expect(sameLayout(PANELS, [...PANELS].reverse())).toBe(true)
    expect(sameLayout(PANELS, PANELS.slice(1))).toBe(false)
    for (const change of [{ x: 1 }, { y: 9 }, { w: 2 }, { h: 'tall' }, { scanner: 'grype' }] as const) {
      expect(sameLayout(PANELS, [{ ...PANELS[1]!, ...change }, PANELS[0]!, PANELS[2]!])).toBe(false)
    }
  })

  it('a full-width panel moves to the left edge, a half one keeps its column', () => {
    const p: DraftPanel = { ...PANELS[2]!, key: 'k' }
    expect(withSettings(p, { w: 2, h: 'short', scanner: null })).toMatchObject({ x: 0, w: 2 })
    expect(withSettings(p, { w: 1, h: 'short', scanner: null })).toMatchObject({ x: 1, w: 1 })
    // a panel with no scanner data gets no scanner key
    expect('scanner' in withSettings(p, { w: 1, h: 'short', scanner: null })).toBe(false)
    expect(withSettings({ ...PANELS[1]!, key: 'k' }, { w: 1, h: 'tall', scanner: 'trivy' })).toMatchObject({
      h: 'tall',
      scanner: 'trivy',
    })
  })

  it('places go to the panels by key, and an unknown key changes nothing', () => {
    const draft: DraftPanel[] = PANELS.map((p, i) => ({ ...p, key: `k${i}` }))
    const out = withPlaces(draft, [
      { key: 'k2', x: 0, y: 20 },
      { key: 'gone', x: 1, y: 1 },
    ])
    expect(out.map((p) => [p.x, p.y])).toEqual([
      [0, 0],
      [0, 7],
      [0, 20],
    ])
  })

  it('each refused save says why, and a lost answer does not say that nothing changed', () => {
    const statuses = [403, 404, 409, 422, 429, 500, 0]
    const copy = statuses.map((s) => saveFailureCopy(s, false))
    expect(new Set([...copy, saveFailureCopy(0, true)]).size).toBe(statuses.length + 1)
    expect(saveFailureCopy(409, false)).toMatch(/changed this dashboard after you opened it/)
    expect(saveFailureCopy(0, false)).not.toMatch(/did not save/)
    expect(saveFailureCopy(504, false)).toBe(saveFailureCopy(0, false))
    expect(saveFailureCopy(503, true)).toMatch(/read-only/)
  })
})

describe('edit mode', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useClusterStore().selectedId = 'c1'
    signIn('lead', ['can_edit_dashboards'])
    resetGridstack()
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(200, doc()))
    vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mockImplementation(async (opts) => {
      const body = (opts as { body: { panels?: DashboardPanel[] } }).body
      return answer(200, doc({ revision: 5, ...(body.panels ? { panels: body.panels } : {}) }))
    })
  })
  afterEach(() => vi.clearAllMocks())

  it('the read page loads no gridstack; Edit dashboard opens edit mode with the settings of Q5', async () => {
    const { w, router } = await mountView()
    expect(gs.inits).toEqual([])
    expect(w.find('.grid-stack').exists()).toBe(false)

    await button(w, 'Edit dashboard').trigger('click')
    await settle()
    expect(router.currentRoute.value.query.edit).toBe('1')
    expect(w.find('h1').text()).toBe('Editing Weekly risk review')
    expect(gs.inits).toEqual([
      expect.objectContaining({
        column: 2,
        cellHeight: 40,
        margin: 15,
        mode: 'top',
        disableResize: true,
        animate: false,
        draggable: { handle: '.dash-move', cancel: 'input,textarea,select,option' },
      }),
    ])
    // each panel has its Move tab, its settings and its remove button at rest
    expect(w.findAll('.dash-move').map((b) => b.attributes('aria-label'))).toEqual([
      'Move Findings summary',
      'Move Top components',
      'Move Triage progress',
    ])
    expect(w.findAll('[aria-label^="Settings of"]')).toHaveLength(3)
    expect(w.findAll('[aria-label^="Remove"]')).toHaveLength(3)
  })

  it('gridstack is imported only by the edit grid, which the page loads on demand', () => {
    const src = (p: string) => readFileSync(resolve(process.cwd(), 'src', p), 'utf8')
    expect(src('views/DashboardView.vue')).not.toMatch(/from 'gridstack'/)
    expect(src('views/DashboardView.vue')).toMatch(/import\('@\/components\/dashboards\/DashboardEditGrid\.vue'\)/)
    expect(src('views/DashboardView.vue')).not.toMatch(/^import DashboardEditGrid/m)
    expect(src('components/dashboards/DashboardEditGrid.vue')).toMatch(/from 'gridstack'/)
  })

  it('a user who cannot change the dashboard gets Edit off, with the reason next to it', async () => {
    signIn('ana', ['can_edit_dashboards'])
    const { w } = await mountView('?edit=1')
    const edit = button(w, 'Edit dashboard')
    expect(edit.attributes('disabled')).toBeDefined()
    expect(edit.attributes('aria-describedby')).toBe('no-edit-note')
    expect(w.find('#no-edit-note').text()).toBe(NO_EDIT_NOTE)
    // ?edit=1 in a link does not open edit mode for them
    expect(gs.inits).toEqual([])
    expect(w.find('h1').text()).toBe('Weekly risk review')
  })

  it('a drop makes the layout unsaved; a save sends the revision and the new panels', async () => {
    const { w } = await mountView('?edit=1')
    expect(w.find('.save-msg').text()).toBe('All changes saved')
    expect(button(w, 'Save changes').attributes('disabled')).toBeDefined()
    expect(button(w, 'Exit edit').attributes('disabled')).toBeUndefined()

    await drop({ 'triage-progress': { x: 0, y: 20 } })
    expect(w.find('.save-msg').text()).toBe('You have unsaved changes')
    // the save bar is the way out of unsaved changes
    expect(button(w, 'Exit edit').attributes('disabled')).toBeDefined()

    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchBody().body.revision).toBe(4)
    expect(patchBody().body.panels).toContainEqual({ panel: 'triage-progress', x: 0, y: 20, w: 1, h: 'short' })
    expect(patchBody().body.panels).toHaveLength(3)
    expect(w.find('.save-msg').text()).toBe('All changes saved')
    expect(useToastStore().toasts.map((t) => t.message)).toEqual(['Dashboard saved.'])

    // the next save sends the revision the last save answered with
    await drop({ 'triage-progress': { x: 1, y: 7 } })
    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchBody().body.revision).toBe(5)
  })

  it('a move made while a save runs stays unsaved, and the next save sends it', async () => {
    let answerSave!: () => void
    vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mockImplementationOnce(
      (opts) =>
        new Promise((done) => {
          const body = (opts as { body: { panels: DashboardPanel[] } }).body
          answerSave = () => done(answer(200, doc({ revision: 5, panels: body.panels })))
        }) as never,
    )
    const { w } = await mountView('?edit=1')
    await drop({ 'triage-progress': { x: 0, y: 20 } })
    await button(w, 'Save changes').trigger('click')
    await drop({ 'top-components': { x: 1, y: 27 } })
    answerSave()
    await flushPromises()
    expect(w.find('.save-msg').text()).toBe('You have unsaved changes')
    expect(button(w, 'Exit edit').attributes('disabled')).toBeDefined()

    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchBody().body.revision).toBe(5)
    expect(patchBody().body.panels).toContainEqual({
      panel: 'top-components',
      x: 1,
      y: 27,
      w: 1,
      h: 'short',
      scanner: 'dashboard',
    })
  })

  it('a save that answers after the user went to another dashboard changes nothing on the page', async () => {
    const other = 'c'.repeat(32)
    let answerSave!: () => void
    vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mockImplementationOnce(
      () => new Promise((done) => (answerSave = () => done(answer(200, doc({ revision: 5 }))))) as never,
    )
    const { w, router } = await mountView('?edit=1')
    await drop({ 'triage-progress': { x: 0, y: 20 } })
    await button(w, 'Save changes').trigger('click')
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(
      answer(200, doc({ dashboard_id: other, name: 'Another board' })),
    )
    await router.push(`/dashboards/${other}`)
    await settle()
    answerSave()
    await flushPromises()
    expect(w.find('h1').text()).toBe('Another board')
    expect(useToastStore().toasts).toEqual([])
  })

  it('the places top mode gives as the grid starts are not a change', async () => {
    gs.compact = (nodes) => nodes.map((n) => (n.el.getAttribute('data-panel') === 'triage-progress' ? { ...n, y: 7 } : n))
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(
      answer(200, doc({ panels: [PANELS[0], PANELS[1], { ...PANELS[2], y: 30 }] })),
    )
    const { w } = await mountView('?edit=1')
    expect(w.find('.save-msg').text()).toBe('All changes saved')
    // a move after it sends the panels where the user sees them
    await drop({ 'top-components': { x: 1, y: 7 }, 'triage-progress': { x: 0, y: 7 } })
    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchBody().body.panels).toContainEqual({ panel: 'triage-progress', x: 0, y: 7, w: 1, h: 'short' })
  })

  it('panel settings change the draft and gridstack: the height, the width and the scanner', async () => {
    const { w } = await mountView('?edit=1')
    await w.find('[aria-label="Settings of Top components"]').trigger('click')
    await flushPromises()
    const panel = w.find('[role="dialog"]')
    expect(panel.text()).toContain('The packages with the most vulnerabilities.')
    const pick = (text: string) => panel.findAll('button').find((b) => b.text() === text)!.trigger('click')
    await pick('Tall')
    await pick('Full')
    await pick('grype')
    expect(panel.text()).toContain('The panel always shows grype.')
    await button(w, 'Apply').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    const id = w.find('[data-panel="top-components"]').attributes('gs-id')
    expect(gs.updates).toEqual([{ id, opts: { x: 0, w: 2, h: 26 } }])
    // the panel reads its new rows and its pinned scanner at once
    expect(JSON.parse(w.find('[data-panel="top-components"] .probe').attributes('data-props')!)).toEqual({
      scanner: 'grype',
      pageSize: 25,
    })

    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchBody().body.panels).toContainEqual({
      panel: 'top-components',
      x: 0,
      y: 7,
      w: 2,
      h: 'tall',
      scanner: 'grype',
    })
  })

  it('a panel with one height and no scanner data shows only the width', async () => {
    const { w } = await mountView('?edit=1')
    await w.find('[aria-label="Settings of Triage progress"]').trigger('click')
    await flushPromises()
    const labels = w.findAll('[role="dialog"] .ui-fld-label').map((l) => l.text())
    expect(labels).toEqual(['Width'])
    await button(w, 'Cancel').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    expect(w.find('.save-msg').text()).toBe('All changes saved')
  })

  it('remove takes the panel out of gridstack and of the save', async () => {
    const { w } = await mountView('?edit=1')
    const id = w.find('[data-panel="triage-progress"]').attributes('gs-id')
    await w.find('[aria-label="Remove Triage progress"]').trigger('click')
    await flushPromises()
    expect(gs.removed).toEqual([id])
    expect(w.find('[data-panel="triage-progress"]').exists()).toBe(false)
    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchBody().body.panels!.map((p) => p.panel)).toEqual(['findings-summary', 'top-components'])
  })

  it('discard starts gridstack again from the saved panels', async () => {
    const { w } = await mountView('?edit=1')
    await w.find('[aria-label="Remove Triage progress"]').trigger('click')
    await drop({ 'top-components': { x: 1, y: 7 } })
    await button(w, 'Discard').trigger('click')
    await settle()
    expect(gs.destroyed).toBe(1)
    expect(gs.inits).toHaveLength(2)
    expect(w.findAll('.grid-stack-item').map((i) => i.attributes('data-panel'))).toEqual(PANELS.map((p) => p.panel))
    expect(w.find('[data-panel="top-components"]').attributes('gs-x')).toBe('0')
    expect(w.find('.save-msg').text()).toBe('All changes saved')
  })

  it('a refused save keeps the changes and says why next to the save bar', async () => {
    vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mockResolvedValue(answer(409))
    const { w } = await mountView('?edit=1')
    await drop({ 'triage-progress': { x: 0, y: 20 } })
    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toBe(saveFailureCopy(409, false))
    expect(w.find('.save-msg').text()).toBe('You have unsaved changes')
    expect(useToastStore().toasts).toEqual([])

    vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mockResolvedValue(
      answer(503, undefined, { type: 'store-read-only' }),
    )
    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toBe(saveFailureCopy(503, true))

    // a discard clears it
    await button(w, 'Discard').trigger('click')
    await settle()
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('Exit edit leaves edit mode and shows the read grid again', async () => {
    const { w, router } = await mountView('?edit=1')
    await button(w, 'Exit edit').trigger('click')
    await settle()
    expect(router.currentRoute.value.query.edit).toBeUndefined()
    expect(gs.destroyed).toBe(1)
    expect(w.find('.grid-stack').exists()).toBe(false)
    expect(w.findAll('.dash-cell')).toHaveLength(3)
  })
})

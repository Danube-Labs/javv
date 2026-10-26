/**
 * The details of a dashboard (issue 440, S8c): its name, description, sharing and opening
 * scanner, a new dashboard, and the remove. The rules in `dashboards/details.ts` are pure and
 * tested as units. The window reads the roles from the server (ruling of 2026-10-26), and edit
 * mode saves the details with the panels, sending only what changed.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('gridstack', () => import('./helpers/fakeGridstack'))

const Probe = defineComponent({ setup: () => () => h('div', { class: 'probe' }) })
vi.mock('@/dashboards/catalog', () => {
  const panels = (): Record<string, unknown> => ({
    'triage-progress': {
      id: 'triage-progress',
      name: 'Triage progress',
      line: 'one line',
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
  deleteDashboardApiV1DashboardsDashboardIdDelete: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listDashboardsApiV1DashboardsGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  createDashboardApiV1DashboardsPost: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  listSharingRolesApiV1DashboardsRolesGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import type { DashboardPanel } from '@/api/generated'
import {
  createDashboardApiV1DashboardsPost,
  deleteDashboardApiV1DashboardsDashboardIdDelete,
  getDashboardApiV1DashboardsDashboardIdGet,
  listDashboardsApiV1DashboardsGet,
  listSharingRolesApiV1DashboardsRolesGet,
  updateDashboardApiV1DashboardsDashboardIdPatch,
} from '@/api/generated'
import DashboardDetailsDialog from '@/components/dashboards/DashboardDetailsDialog.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import {
  NEW_DETAILS,
  NO_NAME_NOTE,
  NO_ROLE_NOTE,
  createFailureCopy,
  detailsChange,
  detailsProblem,
  newDashboardBody,
  removeFailureCopy,
  roleOptions,
  toggled,
  type DashboardDetails,
} from '@/dashboards/details'
import { NO_IMPORT_NOTE } from '@/dashboards/files'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'
import DashboardView from '@/views/DashboardView.vue'
import DashboardsView from '@/views/DashboardsView.vue'

import { resetGridstack } from './helpers/fakeGridstack'

const ID = 'c'.repeat(32)
const PANELS: DashboardPanel[] = [{ panel: 'triage-progress', x: 0, y: 0, w: 1, h: 'short' }]
const doc = (over: Record<string, unknown> = {}) => ({
  dashboard_id: ID,
  name: 'Weekly risk review',
  description: 'For the Monday call',
  owner: 'lead',
  scanner: 'all',
  panels: PANELS,
  sharing: 'roles',
  roles: ['triager'],
  updated_at: new Date().toISOString(),
  updated_by: 'lead',
  revision: 4,
  ...over,
})
const answer = (status: number, data?: unknown, error?: unknown) =>
  ({ data, error, request: {}, response: { ok: status < 300, status } }) as never
const details = (over: Partial<DashboardDetails> = {}): DashboardDetails => ({
  name: 'Weekly risk review',
  description: '',
  scanner: 'all',
  sharing: 'roles',
  roles: ['triager'],
  ...over,
})

function signIn(username: string, capabilities: string[]) {
  useAuthStore().user = { username, role: 'x', capabilities, must_change: false }
}

const button = (w: ReturnType<typeof mount>, text: string) => w.findAll('button').find((b) => b.text() === text)!
const dialogButton = (w: ReturnType<typeof mount>, text: string) =>
  w.find('[role="dialog"]').findAll('button').find((b) => b.text() === text)!

async function mountAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/dashboards', component: DashboardsView },
      { path: '/dashboards/:id', component: DashboardView },
      { path: '/:any(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  const component = path === '/dashboards' ? DashboardsView : DashboardView
  const w = mount(component, { global: { plugins: [router, [PrimeVue, { unstyled: true }]] } })
  await vi.dynamicImportSettled()
  await flushPromises()
  return { w, router }
}

describe('the details rules', () => {
  it('a name is needed, and "Some roles" needs a role', () => {
    expect(detailsProblem(details())).toBeNull()
    expect(detailsProblem(details({ name: '   ' }))).toBe(NO_NAME_NOTE)
    expect(detailsProblem(details({ roles: [] }))).toBe(NO_ROLE_NOTE)
    expect(detailsProblem(details({ sharing: 'everyone', roles: [] }))).toBeNull()
  })

  it('a change sends only what changed, and sharing goes with the roles', () => {
    const before = details()
    expect(detailsChange(before, details())).toEqual({})
    // the texts are trimmed, so spaces alone are not a change
    expect(detailsChange(before, details({ name: ' Weekly risk review ' }))).toEqual({})
    expect(detailsChange(before, details({ name: 'Monday review' }))).toEqual({ name: 'Monday review' })
    expect(detailsChange(before, details({ scanner: 'grype' }))).toEqual({ scanner: 'grype' })
    // "Everyone" clears the roles: the backend refuses roles with any other sharing
    expect(detailsChange(before, details({ sharing: 'everyone' }))).toEqual({ sharing: 'everyone', roles: [] })
    expect(detailsChange(before, details({ roles: ['triager', 'viewer'] }))).toEqual({
      sharing: 'roles',
      roles: ['triager', 'viewer'],
    })
    // the order of the roles is not a change
    const two = details({ roles: ['viewer', 'triager'] })
    expect(detailsChange(two, details({ roles: ['triager', 'viewer'] }))).toEqual({})
  })

  it('a new dashboard has no panels and only the roles of "Some roles"', () => {
    expect(newDashboardBody({ ...NEW_DETAILS, name: ' Mine ', sharing: 'everyone', roles: ['viewer'] })).toEqual({
      name: 'Mine',
      description: '',
      scanner: 'all',
      sharing: 'everyone',
      roles: [],
      panels: [],
    })
  })

  it('the window offers the listed roles and a saved role that the list does not have', () => {
    expect(roleOptions(['admin', 'triager'], ['old_role', 'triager']).map((o) => o.value)).toEqual([
      'admin',
      'triager',
      'old_role',
    ])
    expect(toggled(['a'], 'b')).toEqual(['a', 'b'])
    expect(toggled(['a', 'b'], 'a')).toEqual(['b'])
  })

  it('each refused create or remove says why, and a lost answer does not say that nothing happened', () => {
    for (const copy of [createFailureCopy, removeFailureCopy]) {
      const statuses = [403, 409, 422, 429, 500, 0]
      expect(new Set([...statuses.map((s) => copy(s, false)), copy(0, true)]).size).toBeGreaterThanOrEqual(5)
      expect(copy(0, false)).toMatch(/possibly/)
      expect(copy(504, false)).toBe(copy(0, false))
      expect(copy(503, true)).toMatch(/read-only/)
    }
    expect(removeFailureCopy(409, false)).toMatch(/changed this dashboard after you opened it/)
  })
})

describe('the details window', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(listSharingRolesApiV1DashboardsRolesGet).mockResolvedValue(
      answer(200, { roles: ['admin', 'security_lead', 'triager', 'viewer'] }),
    )
  })
  afterEach(() => vi.clearAllMocks())

  const open = async (d: DashboardDetails, mode: 'create' | 'edit' = 'edit') => {
    const w = mount(DashboardDetailsDialog, {
      props: { details: d, mode },
      global: { plugins: [[PrimeVue, { unstyled: true }]] },
    })
    await flushPromises()
    return w
  }
  const roleButtons = (w: ReturnType<typeof mount>) =>
    w.findAll('[role="group"][aria-label="Roles that can see the dashboard"] button')

  it('lists each role of the server, admin too, with the saved ones on', async () => {
    const w = await open(details({ roles: ['triager', 'gone_role'] }))
    expect(roleButtons(w).map((b) => [b.text(), b.attributes('aria-pressed')])).toEqual([
      ['admin', 'false'],
      ['security_lead', 'false'],
      ['triager', 'true'],
      ['viewer', 'false'],
      ['gone_role', 'true'],
    ])
    expect(w.find('label[for="dash-name"]').exists()).toBe(true)
    expect(w.find('input#dash-name').attributes('maxlength')).toBe('128')
    expect(w.find('input#dash-description').attributes('maxlength')).toBe('1024')
    expect(w.find('input#dash-name').classes()).toContain('set-input--prose')
  })

  it('Apply sends the trimmed details; it is off with the reason while a rule is not met', async () => {
    const w = await open(details())
    await w.find('input#dash-name').setValue('  ')
    const apply = button(w, 'Apply')
    expect(apply.attributes('disabled')).toBeDefined()
    expect(apply.attributes('aria-describedby')).toBe('dd-problem')
    expect(w.find('#dd-problem').text()).toBe(NO_NAME_NOTE)

    await w.find('input#dash-name').setValue(' Monday review ')
    await roleButtons(w)[2]!.trigger('click') // triager off: no role left
    expect(w.find('#dd-problem').text()).toBe(NO_ROLE_NOTE)
    await roleButtons(w)[3]!.trigger('click') // viewer on
    await button(w, 'grype').trigger('click')
    expect(button(w, 'Apply').attributes('disabled')).toBeUndefined()
    await button(w, 'Apply').trigger('click')
    expect(w.emitted('apply')).toEqual([
      [{ name: 'Monday review', description: '', scanner: 'grype', sharing: 'roles', roles: ['viewer'] }],
    ])
  })

  it('a role list that did not load says so, and the other fields still work', async () => {
    vi.mocked(listSharingRolesApiV1DashboardsRolesGet).mockResolvedValue(answer(503))
    const w = await open(details())
    expect(w.find('[role="alert"]').text()).toMatch(/.+/)
    // the saved role still shows, so the window does not drop it
    expect(roleButtons(w).map((b) => b.text())).toEqual(['triager'])
    await button(w, 'Everyone').trigger('click')
    await button(w, 'Apply').trigger('click')
    expect(w.emitted('apply')![0]![0]).toMatchObject({ sharing: 'everyone', roles: [] })
  })

  it('create mode names its button Create', async () => {
    const w = await open(NEW_DETAILS, 'create')
    expect(w.find('h3').text()).toBe('New dashboard')
    expect(button(w, 'Create').attributes('disabled')).toBeDefined()
  })
})

describe('a SettingsInput for text', () => {
  it('opens the text keyboard, and only a number field opens the number one', () => {
    const text = mount(SettingsInput, { props: { modelValue: '', maxlength: 9 } })
    expect(text.find('input').attributes('inputmode')).toBeUndefined()
    expect(text.find('input').attributes('maxlength')).toBe('9')
    const num = mount(SettingsInput, { props: { modelValue: '7', num: true } })
    expect(num.find('input').attributes('inputmode')).toBe('decimal')
    // a name or a description is set in the UI face; a settings value keeps the mono one
    expect(mount(SettingsInput, { props: { modelValue: '', prose: true } }).find('input').classes()).toContain(
      'set-input--prose',
    )
    expect(text.find('input').classes()).not.toContain('set-input--prose')
  })
})

describe('the details in edit mode, and the remove', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useClusterStore().selectedId = 'c1'
    signIn('lead', ['can_edit_dashboards'])
    resetGridstack()
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(200, doc()))
    vi.mocked(listSharingRolesApiV1DashboardsRolesGet).mockResolvedValue(
      answer(200, { roles: ['admin', 'triager', 'viewer'] }),
    )
    vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mockImplementation(async (opts) => {
      const body = (opts as { body: Record<string, unknown> }).body
      const { revision: _r, ...fields } = body
      return answer(200, doc({ ...fields, revision: 5 }))
    })
  })
  afterEach(() => vi.clearAllMocks())

  const patchBody = () =>
    (vi.mocked(updateDashboardApiV1DashboardsDashboardIdPatch).mock.calls.at(-1)![0] as { body: unknown }).body

  it('applied details are unsaved; the save sends only the changed fields and no panels', async () => {
    const { w } = await mountAt(`/dashboards/${ID}?edit=1`)
    await button(w, 'Name and sharing').trigger('click')
    await flushPromises()
    await w.find('input#dash-name').setValue('Monday review')
    await dialogButton(w, 'Everyone').trigger('click')
    await dialogButton(w, 'Apply').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"]').exists()).toBe(false)
    expect(w.find('h1').text()).toBe('Editing Monday review')
    expect(w.find('.save-msg').text()).toBe('You have unsaved changes')
    expect(button(w, 'Exit edit').attributes('disabled')).toBeDefined()

    await button(w, 'Save changes').trigger('click')
    await flushPromises()
    expect(patchBody()).toEqual({ revision: 4, name: 'Monday review', sharing: 'everyone', roles: [] })
    expect(w.find('.save-msg').text()).toBe('All changes saved')
  })

  it('Discard puts back the saved details', async () => {
    const { w } = await mountAt(`/dashboards/${ID}?edit=1`)
    await button(w, 'Name and sharing').trigger('click')
    await flushPromises()
    await w.find('input#dash-name').setValue('Monday review')
    await dialogButton(w, 'Apply').trigger('click')
    await button(w, 'Discard').trigger('click')
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(w.find('h1').text()).toBe('Editing Weekly risk review')
    expect(w.find('.save-msg').text()).toBe('All changes saved')
  })

  it('Remove asks first, sends the revision it read, and goes to the list', async () => {
    vi.mocked(deleteDashboardApiV1DashboardsDashboardIdDelete).mockResolvedValue(answer(204))
    vi.mocked(listDashboardsApiV1DashboardsGet).mockResolvedValue(answer(200, { dashboards: [] }))
    const { w, router } = await mountAt(`/dashboards/${ID}?edit=1`)
    await button(w, 'Remove').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"] h3').text()).toBe('Remove Weekly risk review?')
    expect(deleteDashboardApiV1DashboardsDashboardIdDelete).not.toHaveBeenCalled()

    await dialogButton(w, 'Remove dashboard').trigger('click')
    await flushPromises()
    expect(vi.mocked(deleteDashboardApiV1DashboardsDashboardIdDelete).mock.calls[0]![0]).toMatchObject({
      path: { dashboard_id: ID },
      query: { revision: 4 },
    })
    expect(router.currentRoute.value.path).toBe('/dashboards')
    expect(useToastStore().toasts.map((t) => t.message)).toEqual(['Dashboard “Weekly risk review” removed'])
  })

  it('a refused remove stays in the window and says why', async () => {
    vi.mocked(deleteDashboardApiV1DashboardsDashboardIdDelete).mockResolvedValue(answer(409))
    const { w, router } = await mountAt(`/dashboards/${ID}?edit=1`)
    await button(w, 'Remove').trigger('click')
    await flushPromises()
    await dialogButton(w, 'Remove dashboard').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"] [role="alert"]').text()).toBe(removeFailureCopy(409, false))
    expect(router.currentRoute.value.path).toBe(`/dashboards/${ID}`)
  })

  it('a dashboard removed by somebody else counts as removed', async () => {
    vi.mocked(deleteDashboardApiV1DashboardsDashboardIdDelete).mockResolvedValue(answer(404))
    vi.mocked(listDashboardsApiV1DashboardsGet).mockResolvedValue(answer(200, { dashboards: [] }))
    const { w, router } = await mountAt(`/dashboards/${ID}?edit=1`)
    await button(w, 'Remove').trigger('click')
    await flushPromises()
    await dialogButton(w, 'Remove dashboard').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/dashboards')
  })
})

describe('New dashboard on the list', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(listDashboardsApiV1DashboardsGet).mockResolvedValue(answer(200, { dashboards: [] }))
    vi.mocked(listSharingRolesApiV1DashboardsRolesGet).mockResolvedValue(answer(200, { roles: ['triager'] }))
    vi.mocked(getDashboardApiV1DashboardsDashboardIdGet).mockResolvedValue(answer(200, doc()))
  })
  afterEach(() => vi.clearAllMocks())

  it('is off for a role without can_edit_dashboards, with the reason', async () => {
    signIn('vic', [])
    const { w } = await mountAt('/dashboards')
    const make = button(w, 'New dashboard')
    expect(make.attributes('disabled')).toBeDefined()
    expect(make.attributes('aria-describedby')).toBe('no-import-note')
    expect(w.find('#no-import-note').text()).toBe(NO_IMPORT_NOTE)
  })

  it('makes the dashboard with no panels and opens it in edit mode', async () => {
    signIn('lead', ['can_edit_dashboards'])
    vi.mocked(createDashboardApiV1DashboardsPost).mockResolvedValue(answer(201, doc({ panels: [] })))
    const { w, router } = await mountAt('/dashboards')
    await w.find('.head-actions').findAll('button').find((b) => b.text() === 'New dashboard')!.trigger('click')
    await flushPromises()
    await w.find('input#dash-name').setValue('Mine')
    await dialogButton(w, 'Create').trigger('click')
    await flushPromises()
    expect(vi.mocked(createDashboardApiV1DashboardsPost).mock.calls[0]![0]).toEqual({
      body: { name: 'Mine', description: '', scanner: 'all', sharing: 'private', roles: [], panels: [] },
    })
    expect(router.currentRoute.value.fullPath).toBe(`/dashboards/${ID}?edit=1`)
  })

  it('a refused create stays in the window with the reason', async () => {
    signIn('lead', ['can_edit_dashboards'])
    vi.mocked(createDashboardApiV1DashboardsPost).mockResolvedValue(answer(422))
    const { w, router } = await mountAt('/dashboards')
    await w.find('.head-actions').findAll('button').find((b) => b.text() === 'New dashboard')!.trigger('click')
    await flushPromises()
    await w.find('input#dash-name').setValue('Mine')
    await dialogButton(w, 'Create').trigger('click')
    await flushPromises()
    expect(w.find('[role="dialog"] .modal-error').text()).toBe(createFailureCopy(422, false))
    expect(router.currentRoute.value.path).toBe('/dashboards')
  })
})

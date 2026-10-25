/**
 * The Dashboards list (issue 440, S7): the Saved views card grid with what the server lets this
 * user see, export with no `can_export` (D7), and import for `can_edit_dashboards` only, with a
 * result for each line of the file. The import sends the file as it is: the generated call would
 * send it as one JSON string, which the backend reads as one line that is not a dashboard.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', () => ({
  listDashboardsApiV1DashboardsGet: vi.fn(),
  importDashboardsApiV1DashboardsImportPost: vi.fn(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import { importDashboardsApiV1DashboardsImportPost, listDashboardsApiV1DashboardsGet } from '@/api/generated'
import ImportDashboardsDialog from '@/components/dashboards/ImportDashboardsDialog.vue'
import { importFailureCopy, lineResultCopy, NO_IMPORT_NOTE } from '@/dashboards/files'
import { useAuthStore } from '@/stores/auth'
import DashboardsView from '@/views/DashboardsView.vue'

const DOCS = [
  {
    dashboard_id: 'a'.repeat(32),
    name: 'Weekly risk review',
    description: 'What the security leads look at on Monday.',
    owner: 'lead',
    panels: [{ panel: 'findings-summary', x: 0, y: 0, w: 2, h: 'short' }],
    sharing: 'roles',
    roles: ['security_lead', 'triager'],
    updated_at: new Date(Date.now() - 2 * 3600_000).toISOString(),
    updated_by: 'lead',
  },
  {
    dashboard_id: 'b'.repeat(32),
    name: 'Mine',
    description: '',
    owner: 'me',
    panels: [],
    sharing: 'private',
    roles: [],
    updated_at: new Date().toISOString(),
    updated_by: 'me',
  },
]

const ok = (data: unknown) => ({ data, request: {}, response: { ok: true, status: 200 } }) as never
const refused = (status: number) => ({ data: undefined, request: {}, response: { ok: false, status } }) as never

function signIn(capabilities: string[]) {
  useAuthStore().user = { username: 'me', role: 'x', capabilities, must_change: false } as never
}

async function mountList() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/dashboards')
  const w = mount(DashboardsView, { global: { plugins: [router, [PrimeVue, { unstyled: true }]] } })
  await flushPromises()
  return { w, router }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.mocked(listDashboardsApiV1DashboardsGet).mockResolvedValue(ok({ dashboards: DOCS }))
})
afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('the list', () => {
  it('shows a card for each dashboard with who can see it, its panels and when it changed', async () => {
    signIn(['can_edit_dashboards'])
    const { w } = await mountList()
    expect(w.find('.head-stat').text()).toBe('2 dashboards')
    const cards = w.findAll('.view-card')
    expect(cards).toHaveLength(2)
    expect(cards[0]!.find('h2').text()).toBe('Weekly risk review')
    expect(cards[0]!.find('.vc-badge').text()).toBe('security_lead, triager')
    expect(cards[0]!.text()).toContain('1 panel · changed 2 hours ago by lead')
    expect(cards[0]!.find('.vc-owner').text()).toBe('owner lead')
    expect(cards[1]!.find('.vc-badge').text()).toBe('Only the owner')
    expect(cards[1]!.text()).toContain('0 panels')
  })

  it('opens a dashboard from its card', async () => {
    signIn([])
    const { w, router } = await mountList()
    const open = w.findAll('.view-card')[0]!.findAll('button').find((b) => b.text() === 'Open')!
    await open.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe(`/dashboards/${'a'.repeat(32)}`)
  })

  it('says it is loading, and a count it has not read is "-", not 0', async () => {
    signIn([])
    vi.mocked(listDashboardsApiV1DashboardsGet).mockImplementationOnce(() => new Promise(() => {}) as never)
    const { w } = await mountList()
    expect(w.find('.head-stat').text()).toBe('- dashboards')
    expect(w.find('[aria-label="Loading dashboards"]').exists()).toBe(true)
  })

  it('a refused read shows why, never "No dashboards"', async () => {
    signIn([])
    vi.mocked(listDashboardsApiV1DashboardsGet).mockResolvedValueOnce(refused(429))
    const { w } = await mountList()
    expect(w.find('.head-stat').text()).toBe('- dashboards')
    expect(w.find('.load-error').text()).toBe('The search backend is busy. Try again in a few seconds.')
    expect(w.text()).not.toContain('No dashboards yet')
  })

  it('an empty list says how to add one', async () => {
    signIn(['can_edit_dashboards'])
    vi.mocked(listDashboardsApiV1DashboardsGet).mockResolvedValueOnce(ok({ dashboards: [] }))
    const { w } = await mountList()
    expect(w.text()).toContain('No dashboards yet')
    expect(w.find('.head-stat').text()).toBe('0 dashboards')
  })
})

describe('export', () => {
  function stubDownload() {
    const fetch = vi.fn(async () => new Response('{}\n', { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    vi.stubGlobal('URL', { ...URL, createObjectURL: () => 'blob:x', revokeObjectURL: () => {} })
    return fetch
  }

  it('a user without can_export can export all, and one dashboard from its card (D7)', async () => {
    signIn([])
    const fetch = stubDownload()
    const { w } = await mountList()
    const all = w.findAll('button').find((b) => b.text().includes('Export all'))!
    expect(all.attributes('disabled')).toBeUndefined()
    await all.trigger('click')
    await flushPromises()
    expect(fetch.mock.calls[0]![0]).toBe('/api/v1/dashboards/export.ndjson?')
    const one = w.findAll('.view-card')[0]!.findAll('button').find((b) => b.text() === 'Export')!
    await one.trigger('click')
    await flushPromises()
    expect(fetch.mock.calls[1]![0]).toBe(`/api/v1/dashboards/export.ndjson?dashboard_id=${'a'.repeat(32)}`)
  })
})

describe('import', () => {
  it('without can_edit_dashboards the button stays, off, with the reason', async () => {
    signIn([])
    const { w } = await mountList()
    const imp = w.findAll('button').find((b) => b.text() === 'Import')!
    expect(imp.attributes('disabled')).toBeDefined()
    expect(imp.attributes('aria-describedby')).toBe('no-import-note')
    expect(w.find('#no-import-note').text()).toBe(NO_IMPORT_NOTE)
  })

  it('with it, the button opens the import dialog', async () => {
    signIn(['can_edit_dashboards'])
    const { w } = await mountList()
    await w.findAll('button').find((b) => b.text() === 'Import')!.trigger('click')
    expect(w.findComponent(ImportDashboardsDialog).exists()).toBe(true)
  })

  async function importFile(text: string, copy: boolean) {
    const w = mount(ImportDashboardsDialog, { global: { plugins: [[PrimeVue, { unstyled: true }]] } })
    const input = w.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [new File([text], 'board.ndjson')] })
    await input.trigger('change')
    if (copy) await w.findAll('button').find((b) => b.text() === 'Make copies')!.trigger('click')
    await w.findAll('button').find((b) => b.text() === 'Import')!.trigger('click')
    await flushPromises()
    return w
  }

  it('sends the file text as it is, and the copy option', async () => {
    const outcome = { results: [{ line: 1, status: 201, dashboard_id: 'c'.repeat(32) }], created: 1, conflicts: 0, invalid: 0 }
    vi.mocked(importDashboardsApiV1DashboardsImportPost).mockResolvedValue(ok(outcome))
    const text = '{"name":"x"}\n{"exported_count":1,"missing_ids":[]}\n'
    const w = await importFile(text, true)
    const opts = vi.mocked(importDashboardsApiV1DashboardsImportPost).mock.calls[0]![0] as {
      body: string
      query?: { copy?: boolean }
      bodySerializer: (b: unknown) => unknown
    }
    expect(opts.body).toBe(text)
    expect(opts.bodySerializer(opts.body)).toBe(text)
    expect(opts.query).toEqual({ copy: true })
    expect(w.emitted('imported')).toEqual([[1]])
  })

  it('shows a result for each line, and the counts', async () => {
    const outcome = {
      results: [
        { line: 1, status: 201, dashboard_id: 'c'.repeat(32) },
        { line: 2, status: 409, dashboard_id: 'd'.repeat(32) },
        { line: 3, status: 422, errors: [{ loc: ['panels', 0, 'panel'], msg: 'Input should be …', type: 'literal_error' }] },
      ],
      created: 1,
      conflicts: 1,
      invalid: 1,
    }
    vi.mocked(importDashboardsApiV1DashboardsImportPost).mockResolvedValue(ok(outcome))
    const w = await importFile('{}\n', false)
    expect(vi.mocked(importDashboardsApiV1DashboardsImportPost).mock.calls[0]![0]).toMatchObject({ query: undefined })
    expect(w.find('[role="status"]').text()).toBe('1 made · 1 with an ID that exists · 1 not correct')
    expect(w.findAll('tbody tr').map((r) => r.text())).toEqual([
      '1Made',
      '2ID exists, not made',
      '3Not correct: a value that JAVV does not know (panel 1, panel)',
    ])
  })

  it('a refused import says why and makes no result list', async () => {
    vi.mocked(importDashboardsApiV1DashboardsImportPost).mockResolvedValue(refused(413))
    const w = await importFile('{}\n', false)
    expect(w.find('.load-error').text()).toBe(importFailureCopy(413))
    expect(w.find('tbody').exists()).toBe(false)
    expect(w.emitted('imported')).toBeUndefined()
  })
})

describe('the words of a result', () => {
  it.each([
    [{ line: 1, status: 201 }, 'Made'],
    [{ line: 1, status: 409 }, 'ID exists, not made'],
    [{ line: 1, status: 422, errors: [{ loc: [], msg: 'x', type: 'json_invalid' }] }, 'Not correct: not a line of JSON'],
    [
      { line: 1, status: 422, errors: [{ loc: ['color'], msg: 'x', type: 'extra_forbidden' }, { loc: ['name'], msg: 'x', type: 'missing' }] },
      'Not correct: a field that a dashboard does not have (color), and 1 more',
    ],
    [{ line: 1, status: 422, errors: [{ loc: ['name'], msg: 'String should have at least 1 character', type: 'string_too_short' }] }, 'Not correct: String should have at least 1 character (name)'],
  ] as const)('%o', (result, words) => {
    expect(lineResultCopy(result as never)).toBe(words)
  })

  it('names each status that has no result for each line', () => {
    expect(importFailureCopy(413)).toContain('1,000 dashboards')
    expect(importFailureCopy(403)).toBe(NO_IMPORT_NOTE)
    expect(importFailureCopy(429)).toBe('The search backend is busy. Try again in a few seconds.')
    expect(importFailureCopy(503)).toContain('The lines before the failure made their dashboards')
  })
})

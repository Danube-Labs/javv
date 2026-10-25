/**
 * The Dashboards list (issue 440, S7): the Saved views card grid with what the server lets this
 * user see, export with no `can_export` (D7), and import for `can_edit_dashboards` only, with a
 * result for each line of the file. The import sends the file as it is: the generated call would
 * send a string as one JSON string, which the backend reads as one line that is not a dashboard,
 * and a text read of the file would change its bytes.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', () => ({
  listDashboardsApiV1DashboardsGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  importDashboardsApiV1DashboardsImportPost: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import { importDashboardsApiV1DashboardsImportPost, listDashboardsApiV1DashboardsGet } from '@/api/generated'
import ImportDashboardsDialog from '@/components/dashboards/ImportDashboardsDialog.vue'
import {
  EMPTY_FILE_NOTE,
  importFailureCopy,
  lineResultCopy,
  NO_IMPORT_NOTE,
  VALUE_ERROR_WORDS,
} from '@/dashboards/files'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
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
    // a long role list ends in "…" in the card; its title keeps the whole list
    expect(cards[0]!.find('.vc-badge-text').attributes('title')).toBe('security_lead, triager')
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
    const fetch = vi.fn<(url: string) => Promise<Response>>(async () => new Response('{}\n', { status: 200 }))
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

  it('the list reads again after each import answer, and names only a count that was made', async () => {
    signIn(['can_edit_dashboards'])
    const { w } = await mountList()
    await w.findAll('button').find((b) => b.text() === 'Import')!.trigger('click')
    w.findComponent(ImportDashboardsDialog).vm.$emit('imported', 0)
    await flushPromises()
    expect(listDashboardsApiV1DashboardsGet).toHaveBeenCalledTimes(2)
    expect(useToastStore().toasts).toEqual([])
    w.findComponent(ImportDashboardsDialog).vm.$emit('imported', 2)
    await flushPromises()
    expect(listDashboardsApiV1DashboardsGet).toHaveBeenCalledTimes(3)
    expect(useToastStore().toasts.map((t) => t.message)).toEqual(['2 dashboards imported'])
  })

  async function importFile(content: BlobPart[], copy: boolean) {
    const w = mount(ImportDashboardsDialog, { global: { plugins: [[PrimeVue, { unstyled: true }]] } })
    const input = w.find('input[type="file"]')
    const file = new File(content, 'board.ndjson')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    if (copy) await w.findAll('button').find((b) => b.text() === 'Make copies')!.trigger('click')
    await w.findAll('button').find((b) => b.text() === 'Import')!.trigger('click')
    await flushPromises()
    return { w, file }
  }

  it('sends the file itself, with its bytes as they are, and the copy option', async () => {
    const outcome = { results: [{ line: 1, status: 201, dashboard_id: 'c'.repeat(32) }], created: 1, conflicts: 0, invalid: 0 }
    vi.mocked(importDashboardsApiV1DashboardsImportPost).mockResolvedValue(ok(outcome))
    // a byte-order mark and a byte that is not UTF-8: a text read would drop the one and replace the other
    const bytes = new Uint8Array([0xef, 0xbb, 0xbf, 0x7b, 0x7d, 0xe9, 0x0a])
    const { w, file } = await importFile([bytes], true)
    const opts = vi.mocked(importDashboardsApiV1DashboardsImportPost).mock.calls[0]![0] as {
      body: unknown
      query?: { copy?: boolean }
      bodySerializer: (b: unknown) => unknown
    }
    expect(opts.body).toBe(file)
    expect(opts.bodySerializer(opts.body)).toBe(file)
    expect(new Uint8Array(await (opts.body as Blob).arrayBuffer())).toEqual(bytes)
    expect(opts.query).toEqual({ copy: true })
    expect(w.emitted('imported')).toEqual([[1]])
  })

  it('an empty file is not sent, and says so', async () => {
    const { w } = await importFile([], false)
    expect(importDashboardsApiV1DashboardsImportPost).not.toHaveBeenCalled()
    expect(w.find('.load-error').text()).toBe(EMPTY_FILE_NOTE)
    expect(w.find('.imp-name').text()).toBe('board.ndjson · 0 bytes')
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
    const { w } = await importFile(['{}\n'], false)
    expect(vi.mocked(importDashboardsApiV1DashboardsImportPost).mock.calls[0]![0]).toMatchObject({ query: undefined })
    expect(w.find('[role="status"]').text()).toBe('1 made · 1 with an ID that exists · 1 not correct')
    expect(w.findAll('tbody tr').map((r) => r.text())).toEqual([
      '1Made',
      '2ID exists, not made',
      '3Not correct: a value that JAVV does not know (panel 1, panel)',
    ])
  })

  it('a refused import says why, makes no result list, and has the list read again', async () => {
    vi.mocked(importDashboardsApiV1DashboardsImportPost).mockResolvedValue(refused(503))
    const { w } = await importFile(['{}\n'], true)
    expect(w.find('.load-error').text()).toBe(importFailureCopy(503, true))
    expect(w.find('tbody').exists()).toBe(false)
    expect(w.emitted('imported')).toEqual([[0]])
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
    [{ line: 1, status: 422, errors: [{ loc: ['panels'], msg: 'List should have at most 24 items after validation, not 30', type: 'too_long' }] }, 'Not correct: too many items (panels)'],
    [{ line: 1, status: 422, errors: [{ loc: ['roles', 1], msg: 'String should have at most 64 characters', type: 'string_too_long' }] }, 'Not correct: String should have at most 64 characters (role 2)'],
    [{ line: 1, status: 422, errors: [{ loc: ['panels', 0], msg: 'Value error, the panel findings-summary has no tall height', type: 'value_error' }] }, 'Not correct: a height that this panel does not have (panel 1)'],
    [{ line: 1, status: 422, errors: [{ loc: [], msg: 'Value error, the panel findings-summary at (1, 7) overlaps', type: 'value_error' }] }, 'Not correct: two panels in the same place'],
    [{ line: 1, status: 422, errors: [{ loc: [], msg: 'Value error, a check that is new', type: 'value_error' }] }, 'Not correct: a value that JAVV cannot use'],
  ] as const)('%o', (result, words) => {
    expect(lineResultCopy(result as never)).toBe(words)
  })

  it('a check of the backend names no value of the file: each one has its own words', () => {
    const source = readFileSync(resolve(process.cwd(), '..', 'backend/src/backend/routers/dashboards.py'), 'utf8')
    const messages = [...source.matchAll(/raise ValueError\(f?"([^"]+)"\)/g)].map((m) => m[1]!.replace(/\{[^}]+\}/g, 'VALUE-FROM-FILE'))
    expect(messages).toHaveLength(5)
    for (const msg of messages) {
      expect({ msg, hasWords: VALUE_ERROR_WORDS.some(([re]) => re.test(msg)) }).toEqual({ msg, hasWords: true })
      const words = lineResultCopy({ line: 1, status: 422, errors: [{ loc: ['panels', 0], msg: `Value error, ${msg}`, type: 'value_error' }] })
      expect(words).not.toContain('VALUE-FROM-FILE')
      expect(words).not.toContain('Value error')
    }
  })

  it('names each status that has no result for each line', () => {
    expect(importFailureCopy(413, false)).toContain('1,000 dashboards')
    expect(importFailureCopy(403, false)).toBe(NO_IMPORT_NOTE)
    expect(importFailureCopy(0, false)).toContain('did not reach JAVV')
    expect(importFailureCopy(200, false)).toContain('its answer could not be read')
    expect(importFailureCopy(415, false)).toBe('JAVV did not import the file. No dashboard was made.')
  })

  it('a failure that stops the import says that the lines before it were made, and what a retry does', () => {
    expect(importFailureCopy(429, true)).toBe(
      'The search backend was busy, so the import stopped. The lines before the failure made their dashboards. ' +
        'If you import the file again with Make copies, JAVV makes those dashboards a second time.',
    )
    expect(importFailureCopy(503, false)).toBe(
      'The import stopped. The lines before the failure made their dashboards. ' +
        'If you import the file again with Keep the IDs, JAVV does not make those dashboards again.',
    )
  })
})

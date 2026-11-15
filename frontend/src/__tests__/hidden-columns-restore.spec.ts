/**
 * A bad stored hidden-columns value does not stop the screen (issue 881). Findings and Running
 * images read the value while they start; a plain JSON.parse threw on garbage, and the page was
 * replaced by the error page at each visit, because the value stays in the browser.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) => {
  const real = await importOriginal<Record<string, unknown>>()
  const refused = { error: { title: 'Too Many Requests' }, request: {}, response: { ok: false, status: 429 } }
  return Object.fromEntries(
    Object.entries(real).map(([name, value]) => [
      name,
      typeof value === 'function' ? vi.fn<() => Promise<never>>(async () => refused as never) : value,
    ]),
  )
})
vi.mock('@/api/client', () => ({ client: {} }))

import { listRunningImagesApiV1ImagesGet, searchFindingsApiV1FindingsGet } from '@/api/generated'
import ColumnsMenu from '@/components/findings/ColumnsMenu.vue'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import ImagesTable from '@/components/images/ImagesTable.vue'
import { useClusterStore } from '@/stores/cluster'
import { useFindingsStore } from '@/stores/findings'
import FindingsView from '@/views/FindingsView.vue'
import ImagesView from '@/views/ImagesView.vue'

const CLUSTER = 'c-k3d-0001'

async function mountRouted(component: Component) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      // a row of the Findings table links to its finding page
      { path: '/findings/:cveId', name: 'finding', component: { template: '<div />' } },
      { path: '/:any(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  const w = mount(component, {
    global: { plugins: [router, [PrimeVue, { unstyled: true }]], stubs: { EChart: true } },
  })
  await flushPromises()
  return w
}

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.clusters = [{ cluster_id: CLUSTER, cluster_name: 'k3d' }] as never
  clusters.selectedId = CLUSTER
  clusters.loaded = true
  // Running images draws its table only for a committed inventory; an empty one is enough
  const inventory = { inventory_run_id: 'r-1', inventory_order: 1, started_at: null, completed_at: null }
  vi.mocked(listRunningImagesApiV1ImagesGet).mockResolvedValue({
    data: { inventory, images: [] },
    request: {},
    response: { ok: true, status: 200 },
  } as never)
})
afterEach(() => localStorage.clear())

/** The hidden set the screen hands its table. */
function hiddenOf(w: Awaited<ReturnType<typeof mountRouted>>, table: Component): string[] {
  return [...(w.findComponent(table).props() as { hidden: ReadonlySet<string> }).hidden]
}

const SCREENS = [
  ['Findings', FindingsView, FindingsTable, 'javv.findings.hidden_cols', ['epss', 'kev', 'current', 'fixed', 'last_scan']],
  ['Running images', ImagesView, ImagesTable, 'javv.images.hidden_cols', []],
] as const

describe.each(SCREENS)('%s: the stored hidden columns', (_name, view, table, key, defaults) => {
  it.each(['not json', '{}', '5', 'null'])('%j gives the default hidden columns', async (raw) => {
    localStorage.setItem(key, raw)
    const w = await mountRouted(view as Component)
    expect(hiddenOf(w, table as Component)).toEqual(defaults)
  })

  it('a stored list keeps only the keys that name a column', async () => {
    localStorage.setItem(key, '["namespace","zombie"]')
    const w = await mountRouted(view as Component)
    expect(hiddenOf(w, table as Component)).toEqual(['namespace'])
  })
})

/** The order the Findings screen hands its table and its Columns menu. */
function findingsOrder(w: Awaited<ReturnType<typeof mountRouted>>) {
  const table = (w.findComponent(FindingsTable).props() as { colOrder: readonly string[] }).colOrder
  const menu = (w.findComponent(ColumnsMenu).props() as { cols: readonly (readonly [string, string])[] }).cols.map(([k]) => k)
  return { table: [...table], menu }
}

/** The query of the last findings read of the screen. */
function lastFindingsQuery(): Record<string, unknown> {
  const call = vi.mocked(searchFindingsApiV1FindingsGet).mock.lastCall
  expect(call).toBeDefined()
  return (call![0] as { query: Record<string, unknown> }).query
}

describe('Findings: the Paths column (issue 1205)', () => {
  // the hidden columns and the order that main stored, before the Paths column
  const MAIN_HIDDEN = '["epss","kev","current","fixed","last_scan"]'
  const MAIN_ORDER = JSON.stringify(['assignee', 'first_seen', 'last_scan', 'epss', 'kev', 'package', 'current',
    'fixed', 'image', 'namespace', 'images', 'scanner', 'sla', 'state'])

  it('a first visit shows Paths, right after Package, in the table and in the menu', async () => {
    const w = await mountRouted(FindingsView)
    expect(hiddenOf(w, FindingsTable)).not.toContain('paths')
    const { table, menu } = findingsOrder(w)
    expect(table[table.indexOf('package') + 1]).toBe('paths')
    expect(menu).toEqual(table)
  })

  it('a user with hidden columns and an order stored before PR B sees Paths after Package', async () => {
    localStorage.setItem('javv.findings.hidden_cols', MAIN_HIDDEN)
    localStorage.setItem('javv.findings.col_order', MAIN_ORDER)
    const w = await mountRouted(FindingsView)
    expect(hiddenOf(w, FindingsTable)).toEqual(['epss', 'kev', 'current', 'fixed', 'last_scan'])
    const { table } = findingsOrder(w)
    expect(table[0]).toBe('assignee')
    expect(table[table.indexOf('package') + 1]).toBe('paths')
  })

  it('a refused page 2 holds no rows: a hide reads nothing, a show reads the page again with its cursor', async () => {
    const w = await mountRouted(FindingsView)
    expect(lastFindingsQuery().locations).toBe(true)
    // page 2: the page holds a cursor, whose search can expire while the user reads
    const grid = useFindingsStore()
    grid.setResult([], 60, 'c-page-2', true)
    grid.goNext()
    await flushPromises()
    expect(lastFindingsQuery()).toMatchObject({ cursor: 'c-page-2', locations: true })
    const reads = vi.mocked(searchFindingsApiV1FindingsGet).mock.calls.length

    w.findComponent(ColumnsMenu).vm.$emit('toggleCol', 'paths')
    await flushPromises()
    expect(hiddenOf(w, FindingsTable)).toContain('paths')
    expect(vi.mocked(searchFindingsApiV1FindingsGet).mock.calls.length).toBe(reads)

    w.findComponent(ColumnsMenu).vm.$emit('toggleCol', 'paths')
    await flushPromises()
    expect(vi.mocked(searchFindingsApiV1FindingsGet).mock.calls.length).toBe(reads + 1)
    expect(lastFindingsQuery()).toMatchObject({ cursor: 'c-page-2', locations: true })
  })

  it('a stored hidden list with Paths: the read does not ask for the paths', async () => {
    localStorage.setItem('javv.findings.hidden_cols', '["paths"]')
    await mountRouted(FindingsView)
    expect(lastFindingsQuery()).not.toHaveProperty('locations')
  })

  // a read that answers: 60 findings, the next page behind the cursor `c-page-2`
  const answer = (rows: Record<string, unknown>[]) =>
    ({ data: { data: rows, total: { value: 60 }, next_cursor: 'c-page-2' }, request: {}, response: { ok: true, status: 200 } }) as never
  const ROW = {
    finding_key: 'k1', cve_id: 'CVE-2022-23218', scanner: 'grype', severity: 'Critical', severity_canonical: 'critical',
    image_repo: 'docker.io/library/tomcat', tag: '9.0.50-jdk11', package_name: 'libc6', installed_version: '2.28-10',
    fixed_version: null, fixable: false, epss: null, kev: false, ptype: 'deb', state: 'open', overdue: false, due_at: null,
    locations_total: 4,
  }
  /** Page 2 of a list whose reads answer with `rows`; the API mock goes back to refusals after. */
  async function onPage2(rows: Record<string, unknown>[], run: (w: Awaited<ReturnType<typeof mountRouted>>) => Promise<void>) {
    const search = vi.mocked(searchFindingsApiV1FindingsGet)
    const refuse = search.getMockImplementation()!
    search.mockResolvedValue(answer(rows))
    try {
      const w = await mountRouted(FindingsView)
      useFindingsStore().goNext()
      await flushPromises()
      expect(lastFindingsQuery()).toMatchObject({ cursor: 'c-page-2' })
      await run(w)
    } finally {
      search.mockImplementation(refuse)
    }
  }
  const toggle = async (w: Awaited<ReturnType<typeof mountRouted>>) => {
    w.findComponent(ColumnsMenu).vm.$emit('toggleCol', 'paths')
    await flushPromises()
  }

  it('rows read with their paths: a hide and a show of Paths read nothing (ruling of 2026-11-15, option 3)', async () => {
    await onPage2([{ ...ROW, locations: ['/usr/share/doc/libc6/copyright', '/var/lib/dpkg/status'] }], async (w) => {
      const reads = vi.mocked(searchFindingsApiV1FindingsGet).mock.calls.length
      await toggle(w)
      expect(hiddenOf(w, FindingsTable)).toContain('paths')
      await toggle(w)
      expect(hiddenOf(w, FindingsTable)).not.toContain('paths')
      expect(vi.mocked(searchFindingsApiV1FindingsGet).mock.calls.length).toBe(reads)
      const rows = (w.findComponent(FindingsTable).props() as { rows: { locations?: unknown }[] }).rows
      expect(rows[0]!.locations).toEqual(['/usr/share/doc/libc6/copyright', '/var/lib/dpkg/status'])
    })
  })

  it('rows read without their paths: a show of Paths reads the page again with its cursor (option 3)', async () => {
    localStorage.setItem('javv.findings.hidden_cols', '["paths"]')
    await onPage2([ROW], async (w) => {
      expect(lastFindingsQuery()).not.toHaveProperty('locations')
      const reads = vi.mocked(searchFindingsApiV1FindingsGet).mock.calls.length
      await toggle(w)
      expect(vi.mocked(searchFindingsApiV1FindingsGet).mock.calls.length).toBe(reads + 1)
      expect(lastFindingsQuery()).toMatchObject({ cursor: 'c-page-2', locations: true })
    })
  })
})

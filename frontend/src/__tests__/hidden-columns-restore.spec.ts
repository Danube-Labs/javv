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

import { listRunningImagesApiV1ImagesGet } from '@/api/generated'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import ImagesTable from '@/components/images/ImagesTable.vue'
import { useClusterStore } from '@/stores/cluster'
import FindingsView from '@/views/FindingsView.vue'
import ImagesView from '@/views/ImagesView.vue'

const CLUSTER = 'c-k3d-0001'

async function mountRouted(component: Component) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
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

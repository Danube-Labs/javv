/**
 * The Saved views list (SCREENS §6, issue 1004): the whole card opens the view. Its link is the
 * /findings address of the view's filters, so a ctrl click opens them in a new tab, and a plain
 * click applies the whole view first (the columns, the density, the sort and the time window),
 * as the Open in Findings button did.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', () => ({
  listViewsApiV1ViewsGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  facetFindingsApiV1FindingsFacetsGet: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
  deleteViewApiV1ViewsViewIdDelete: vi.fn<(...args: unknown[]) => Promise<unknown>>(),
}))
vi.mock('@/api/client', () => ({ client: {} }))

import { listViewsApiV1ViewsGet } from '@/api/generated'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { FINDINGS_DENSE_KEY, presetToRouteQuery } from '@/findings/savedViews'
import { useAuthStore } from '@/stores/auth'
import SavedViewsView from '@/views/SavedViewsView.vue'

const PRESET = { severity: ['critical', 'high'], namespace: ['payments'] }
const VIEW = {
  view_id: 'v'.repeat(32),
  name: 'Prod backlog',
  description: 'payments namespace',
  owner: 'lead',
  preset: PRESET,
  workbench: { dense: true },
}

async function mountList() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/views')
  const w = mount(SavedViewsView, { global: { plugins: [router, [PrimeVue, { unstyled: true }]] } })
  await flushPromises()
  return { w, router }
}

beforeEach(() => {
  setActivePinia(createPinia())
  useAuthStore().user = { username: 'me', role: 'x', capabilities: [], must_change: false } as never
  vi.mocked(listViewsApiV1ViewsGet).mockResolvedValue({
    data: { views: [VIEW] },
    request: {},
    response: { ok: true, status: 200 },
  } as never)
  localStorage.clear()
})
afterEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})

describe('the Saved views card', () => {
  it('links to the /findings address of the view, with no Open in Findings button', async () => {
    const { w, router } = await mountList()
    const card = w.get('.view-card')
    expect(card.findAll('button').map((b) => b.text())).not.toContain('Open in Findings')
    const href = router.resolve({ path: '/findings', query: presetToRouteQuery(FINDINGS_FIELDS, PRESET as never) }).href
    expect(card.get('a.vc-link').attributes('href')).toBe(href)
    expect(card.get('.vc-open').text()).toBe('Open in Findings ›')
  })

  it('a plain click applies the whole view, then opens Findings with its filters', async () => {
    const { w, router } = await mountList()
    await w.get('a.vc-link').trigger('click', { button: 0 })
    await flushPromises()
    expect(localStorage.getItem(FINDINGS_DENSE_KEY)).toBe('true')
    expect(router.currentRoute.value.path).toBe('/findings')
    expect(router.currentRoute.value.query).toEqual(presetToRouteQuery(FINDINGS_FIELDS, PRESET as never))
  })

  it('a ctrl click is left to the browser: this tab stays, nothing is applied here', async () => {
    const { w, router } = await mountList()
    await w.get('a.vc-link').trigger('click', { button: 0, ctrlKey: true })
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/views')
    expect(localStorage.getItem(FINDINGS_DENSE_KEY)).toBeNull()
  })
})

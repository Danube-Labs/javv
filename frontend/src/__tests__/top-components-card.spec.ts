/**
 * Top components on Overview and as a dashboard panel, paged with the shared GridPager (issue
 * 1190, row 13: the paging is the shared usePagedSlice).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    topComponentsFindingsApiV1FindingsTopComponentsGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { topComponentsFindingsApiV1FindingsTopComponentsGet } from '@/api/generated'
import TopComponentsCard from '@/components/overview/TopComponentsCard.vue'
import { useClusterStore } from '@/stores/cluster'

import { bodyRows, nextPage, pagerText, pickRowsPerPage } from './helpers/pager'

// trivy ranks the packages 0, 1, 2 …; grype has CVEs for the first 12 packages only
const component = (i: number) => ({
  package_name: `pkg-${i}`,
  count: 100 - i,
  unique_cves_by_scanner: { trivy: 100 - i, ...(i < 12 ? { grype: 50 - i } : {}) },
})

async function mountCard(props: Record<string, unknown> = {}) {
  vi.mocked(topComponentsFindingsApiV1FindingsTopComponentsGet).mockResolvedValue({
    data: { components: Array.from({ length: 30 }, (_, i) => component(i)) },
    response: { ok: true, status: 200 },
  } as never)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { render: () => null } }],
  })
  const w = mount(TopComponentsCard, { props: { scanner: 'trivy', ...props }, global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('TopComponentsCard paging', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useClusterStore().selectedId = 'c-k3d-0001'
  })

  it('shows 10 packages, then the next 10', async () => {
    const w = await mountCard()
    expect(pagerText(w)).toBe('Rows 1 to 10 of 30')
    expect(bodyRows(w)).toBe(10)
    await nextPage(w)
    expect(pagerText(w)).toBe('Rows 11 to 20 of 30')
  })

  it('a new number of rows per page shows page 1 with that number of rows', async () => {
    const w = await mountCard()
    await nextPage(w)
    await pickRowsPerPage(w, 25)
    expect(pagerText(w)).toBe('Rows 1 to 25 of 30')
    expect(bodyRows(w)).toBe(25)
  })

  it('another scanner ranks the board again and shows page 1', async () => {
    const w = await mountCard()
    await nextPage(w)
    await w.setProps({ scanner: 'grype' })
    expect(pagerText(w)).toBe('Rows 1 to 10 of 12')
  })

  it('a tall dashboard panel opens with its own number of rows', async () => {
    const w = await mountCard({ pageSize: 25 })
    expect(pagerText(w)).toBe('Rows 1 to 25 of 30')
    expect(bodyRows(w)).toBe(25)
  })

  it('a dashboard panel of a new height shows page 1 with its rows', async () => {
    const w = await mountCard()
    await nextPage(w)
    await w.setProps({ pageSize: 25 })
    expect(pagerText(w)).toBe('Rows 1 to 25 of 30')
  })
})

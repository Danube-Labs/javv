/**
 * Riskiest images on Overview and as a dashboard panel, paged with the shared GridPager (issue
 * 1190, row 13: the paging is the shared usePagedSlice).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listRunningImagesApiV1ImagesGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { listRunningImagesApiV1ImagesGet } from '@/api/generated'
import RiskiestImagesCard from '@/components/overview/RiskiestImagesCard.vue'
import { useClusterStore } from '@/stores/cluster'

import { bodyRows, nextPage, pagerText, pickRowsPerPage } from './helpers/pager'

// trivy has critical findings in all 30 images; grype has them in the first 12 only
const image = (i: number) => ({
  image_digest: `sha256:${String(i).padStart(64, '0')}`,
  image_repo: `repo-${i}`,
  tag: 'v1',
  namespaces: ['payments'],
  scanners: ['trivy', 'grype'],
  severity_by_scanner: { trivy: { crit: 100 - i }, ...(i < 12 ? { grype: { crit: 50 - i } } : {}) },
})

async function mountCard(props: Record<string, unknown> = {}) {
  vi.mocked(listRunningImagesApiV1ImagesGet).mockResolvedValue({
    data: { images: Array.from({ length: 30 }, (_, i) => image(i)), inventory: {} },
    response: { ok: true, status: 200 },
  } as never)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { render: () => null } }],
  })
  const w = mount(RiskiestImagesCard, { props: { scanner: 'trivy', ...props }, global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('RiskiestImagesCard paging', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useClusterStore().selectedId = 'c-k3d-0001'
  })

  it('shows 10 images, then the next 10', async () => {
    const w = await mountCard()
    expect(pagerText(w)).toBe('Showing 1–10 of 30')
    expect(bodyRows(w)).toBe(10)
    await nextPage(w)
    expect(pagerText(w)).toBe('Showing 11–20 of 30')
  })

  it('a new number of rows per page shows page 1 with that number of rows', async () => {
    const w = await mountCard()
    await nextPage(w)
    await pickRowsPerPage(w, 25)
    expect(pagerText(w)).toBe('Showing 1–25 of 30')
    expect(bodyRows(w)).toBe(25)
  })

  it('another scanner ranks the board again and shows page 1', async () => {
    const w = await mountCard()
    await nextPage(w)
    await w.setProps({ scanner: 'grype' })
    expect(pagerText(w)).toBe('Showing 1–10 of 12')
  })

  it('a tall dashboard panel opens with its own number of rows', async () => {
    const w = await mountCard({ pageSize: 25 })
    expect(pagerText(w)).toBe('Showing 1–25 of 30')
    expect(bodyRows(w)).toBe(25)
  })

  it('a dashboard panel of a new height shows page 1 with its rows', async () => {
    const w = await mountCard()
    await nextPage(w)
    await w.setProps({ pageSize: 25 })
    expect(pagerText(w)).toBe('Showing 1–25 of 30')
  })
})

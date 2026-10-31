/**
 * Running images: the menu and the filter list search all the rows the browser holds for a value
 * past the top 32 (issue 1064). The Image list of 40 images stops at 32, so its group gets the
 * search box of the filter list (Q1 option B), with the same search as the menu.
 *
 * The test router has `image-detail`, the route each row links to. Without it, the row link
 * cannot resolve, and the table redraws its columns until Vue stops it ("Maximum recursive
 * updates exceeded in component <DataTable>").
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) => {
  const real = await importOriginal<Record<string, unknown>>()
  return Object.fromEntries(
    Object.entries(real).map(([name, value]) => [
      name,
      typeof value === 'function' ? vi.fn<() => Promise<never>>(() => new Promise<never>(() => {})) : value,
    ]),
  )
})
vi.mock('@/api/client', () => ({ client: {} }))

import { listRunningImagesApiV1ImagesGet } from '@/api/generated'
import type { ValueSearchFn } from '@/filters/facets'
import { IMAGES_FIELDS } from '@/images/fields.config'
import { useClusterStore } from '@/stores/cluster'
import ImagesView from '@/views/ImagesView.vue'

const CLUSTER = 'c-k3d-0001'
const REPO = IMAGES_FIELDS.find((f) => f.key === 'repo')!

const image = (i: number) => ({
  image_digest: `sha256:${i}`,
  image_repo: `docker.io/team/app-${String(i).padStart(2, '0')}`,
  tag: '1.0',
  namespaces: ['shop'],
  scanners: ['trivy'],
  crit: 0,
  high: 0,
  med: 0,
  low: 0,
  negligible: 0,
  unknown: 0,
  total: 0,
  fixable: 0,
  replicas: 1,
  trivy_count: null,
  grype_count: null,
  count_delta: null,
  '@timestamp': '2026-10-30T10:00:00+00:00',
})

async function mountImages() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/images/:digest', name: 'image-detail', component: { template: '<div />' } },
      { path: '/:any(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  const w = mount(ImagesView, {
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
  const inventory = { inventory_run_id: 'r-1', inventory_order: 1, started_at: null, completed_at: null }
  vi.mocked(listRunningImagesApiV1ImagesGet).mockResolvedValue({
    data: { inventory, images: Array.from({ length: 40 }, (_, i) => image(i)) },
    request: {},
    response: { ok: true, status: 200 },
  } as never)
})

describe('Running images: a value past the top 32 (issue 1064)', () => {
  it('the filter list gets the search of the menu, and it finds an image past the top 32', async () => {
    const w = await mountImages()
    const search = w.findComponent({ name: 'FilterBar' }).props('searchValues') as ValueSearchFn
    expect(w.findComponent({ name: 'FacetRail' }).props('searchValues')).toBe(search)
    const found = await search(REPO, 'app-39')
    expect(found?.buckets.map((b) => b.key)).toEqual(['docker.io/team/app-39'])
  })

  it('the table shows the first page of the 40 images', async () => {
    const w = await mountImages()
    expect(w.findAll('.tbl tbody tr')).toHaveLength(25)
  })

  it('the Image group, at its cap, has the search box', async () => {
    const w = await mountImages()
    const titles = w.findAll('.facet .facet-title').map((t) => t.text())
    const group = w.findAll('.facet').at(titles.indexOf('Image'))!
    expect(group.find('.facet-vsearch input').attributes('placeholder')).toBe('Find an image…')
  })
})

/**
 * The About page (issue 341): the Running stack card reads the cluster the top bar has selected,
 * and the links card points at the operator docs in the repo (the docs site joins them once
 * issue 639 lands; the live `/docs` reference once issue 452 routes it). External links open in a
 * new tab without handing it this window (`noopener`).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import AboutLinksCard from '@/components/about/AboutLinksCard.vue'
import AboutView from '@/views/AboutView.vue'
import { useClusterStore } from '@/stores/cluster'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    getMetaApiV1MetaGet: vi.fn<() => Promise<unknown>>(() => new Promise(() => {})),
    scannerProvenanceApiV1ScannersProvenanceGet: vi.fn<() => Promise<unknown>>(
      () => new Promise(() => {}),
    ),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})

beforeEach(() => setActivePinia(createPinia()))

describe('AboutView', () => {
  it('hands the Running stack card the selected cluster', async () => {
    const clusters = useClusterStore()
    clusters.clusters = [{ cluster_id: 'c-1', cluster_name: 'prod-eu' }] as never
    clusters.selectedId = 'c-1'
    const w = mount(AboutView, { global: { plugins: [router] } })
    await flushPromises()
    const card = w.findComponent({ name: 'RunningStackCard' })
    expect(card.props()).toEqual({ clusterId: 'c-1', clusterName: 'prod-eu' })
    expect(w.find('h1').text()).toBe('About')
  })
})

describe('AboutLinksCard', () => {
  it('links the upgrade guide, image verification and the API reference in the repo', () => {
    const w = mount(AboutLinksCard)
    const links = w.findAll('a.about-link').map((a) => ({
      href: a.attributes('href'),
      target: a.attributes('target'),
      rel: a.attributes('rel'),
    }))
    const repo = 'https://github.com/Danube-Labs/javv/blob/main'
    expect(links.map((l) => l.href)).toEqual([
      `${repo}/docs/UPGRADING.md`,
      `${repo}/scanner/README.md#verify-a-published-image`,
      `${repo}/docs/API.md`,
    ])
    for (const l of links) {
      expect(l.target).toBe('_blank')
      expect(l.rel).toContain('noopener')
    }
  })
})

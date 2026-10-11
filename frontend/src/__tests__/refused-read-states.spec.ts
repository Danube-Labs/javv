/**
 * A refused read is not an empty answer (issue 817, finding 5). A 429 on the findings search showed
 * the right alert, but also "0 findings" and "No findings yet" under it, while the facets counted
 * 508. Here every SDK call is refused: each grid shows its failure copy, and neither its head count
 * nor its table claims there is nothing.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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

import AuditTable from '@/components/audit/AuditTable.vue'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import { useClusterStore } from '@/stores/cluster'
import ApprovalsView from '@/views/ApprovalsView.vue'
import AuditTrailView from '@/views/AuditTrailView.vue'
import ContributorsView from '@/views/ContributorsView.vue'
import FindingsView from '@/views/FindingsView.vue'
import ImagesView from '@/views/ImagesView.vue'

const CLUSTER = 'c-k3d-0001'

async function mountRouted(component: Component, props: Record<string, unknown> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/')
  return mount(component, { props, global: { plugins: [router], stubs: { EChart: true } } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.clusters = [{ cluster_id: CLUSTER, cluster_name: 'k3d' }] as never
  clusters.selectedId = CLUSTER
  clusters.loaded = true
})

describe('a grid whose read is refused says so, and claims no empty answer', () => {
  // what each grid showed on a refused read before this change is in the comment
  it.each([
    // alert right, but "0 findings" and "No findings yet. The first committed scan…" under it
    ['Findings', FindingsView, 'The search backend is busy.', /(?<!\d)0 findings/, ['No findings yet']],
    // "0 events" and "No journaled activity for this cluster yet."
    ['Audit log', AuditTrailView, 'Audit log unavailable.', /(?<!\d)0 events/, ['No journaled activity']],
    // "0 contributors"
    ['Contributors', ContributorsView, 'Contributors unavailable.', /(?<!\d)0 contributors/, []],
    // "0 standing acceptances"
    ['Approvals', ApprovalsView, 'Could not load the queue.', /(?<!\d)0 standing acceptances/, []],
    // already right: no count, no empty claim
    ['Running images', ImagesView, 'Inventory unavailable.', /(?<!\d)0 images/, []],
  ] as const)('%s', async (_name, view, failure, zeroCount, emptyClaims) => {
    const w = await mountRouted(view as Component)
    await flushPromises()
    await flushPromises()
    const text = w.text()
    expect(text).toContain(failure)
    expect(text).not.toMatch(zeroCount)
    expect(emptyClaims.filter((claim) => text.includes(claim))).toEqual([])
  })
})

describe('the tables tell a refused read from an empty answer', () => {
  it('FindingsTable', async () => {
    const props = { rows: [], sort: 'severity', order: 'desc', loading: false, settled: true } as const
    const empty = await mountRouted(FindingsTable as Component, props)
    expect(empty.text()).toContain('No findings yet.')
    const refused = await mountRouted(FindingsTable as Component, { ...props, failed: true })
    expect(refused.text()).toContain('Findings could not be loaded.')
    expect(refused.text()).not.toContain('No findings')
  })

  it('AuditTable', async () => {
    const empty = await mountRouted(AuditTable as Component, { rows: [], loading: false })
    expect(empty.text()).toContain('No journaled activity for this cluster yet.')
    const refused = await mountRouted(AuditTable as Component, { rows: [], loading: false, failed: true })
    expect(refused.text()).toContain('Events could not be loaded.')
    expect(refused.text()).not.toContain('No journaled activity')
  })
})

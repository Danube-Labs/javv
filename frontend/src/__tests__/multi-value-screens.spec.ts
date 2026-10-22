/**
 * The Audit log and Approvals filters take several values (issue 952). Mounted through each
 * view, so the test covers what the views pass: the list reaches the API, and a link with more
 * values than the API takes keeps 32, with the note in the rail. A view that forgot its cap
 * would send 40 values and get a 422 with nothing on screen.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    approvalListApiV1DecisionsApprovalsGet: vi.fn<() => Promise<unknown>>(),
    auditFacetsApiV1AuditFacetsGet: vi.fn<() => Promise<unknown>>(),
    readAuditLogApiV1AuditGet: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import {
  approvalListApiV1DecisionsApprovalsGet,
  auditFacetsApiV1AuditFacetsGet,
  readAuditLogApiV1AuditGet,
} from '@/api/generated'
import FilterBar from '@/components/filters/FilterBar.vue'
import { useClusterStore } from '@/stores/cluster'
import ApprovalsView from '@/views/ApprovalsView.vue'
import AuditTrailView from '@/views/AuditTrailView.vue'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })
const CLUSTER = 'c-k3d-0001'
const forty = Array.from({ length: 40 }, (_, i) => `u${i}`)

async function mountAt(component: Component, query: Record<string, string>) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/findings', name: 'findings', component: { template: '<div />' } },
      { path: '/findings/:cveId', name: 'finding', component: { template: '<div />' } },
      { path: '/:any(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push({ path: '/', query })
  const w = mount(component, {
    global: { plugins: [router, [PrimeVue, { unstyled: true }]], stubs: { EChart: true } },
  })
  await flushPromises()
  return w
}

/** the `query` of the last call to a mocked SDK function */
const lastQuery = (fn: unknown) =>
  (vi.mocked(fn as (o: { query: Record<string, unknown> }) => unknown).mock.calls.at(-1)?.[0]
    ?.query ?? {}) as Record<string, unknown>

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  const clusters = useClusterStore()
  clusters.clusters = [{ cluster_id: CLUSTER, cluster_name: 'k3d' }] as never
  clusters.selectedId = CLUSTER
  clusters.loaded = true
  vi.mocked(approvalListApiV1DecisionsApprovalsGet).mockResolvedValue(
    ok({ approvals: [], total: 0, facets: { status: [], created_by: [], scanner: [] } }) as never,
  )
  vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValue(ok({ facets: {}, activity: [] }) as never)
  vi.mocked(readAuditLogApiV1AuditGet).mockResolvedValue(
    ok({ data: [], next_cursor: null, total: { value: 0, relation: 'eq' } }) as never,
  )
})

describe('Approvals: Status and Approver take several values', () => {
  it('sends every picked status and approver; scanner stays one value', async () => {
    await mountAt(ApprovalsView, { status: 'expired,open-ended', approver: 'ann,bob', scanner: 'trivy' })
    const q = lastQuery(approvalListApiV1DecisionsApprovalsGet)
    expect(q.status).toEqual(['expired', 'open-ended'])
    expect(q.created_by).toEqual(['ann', 'bob'])
    expect(q.scanner).toBe('trivy')
  })

  it('a link with 40 approvers keeps 32, and the rail says why', async () => {
    const w = await mountAt(ApprovalsView, { approver: forty.join(',') })
    expect(lastQuery(approvalListApiV1DecisionsApprovalsGet).created_by).toEqual(forty.slice(0, 32))
    const note = w.find('.facet-cap[role="status"]')
    expect(note.exists()).toBe(true)
    expect(note.text()).toBe('A filter takes at most 32 values.')
    expect(w.findComponent(FilterBar).props('maxValues')).toBe(32) // the edit box says it too
  })

  it('a cell pick in the queue table adds a second approver', async () => {
    const row = (id: string, by: string) => ({
      decision_id: id, cve_id: `CVE-2026-000${id}`, type: 'risk_accepted',
      scope: { namespaces: [], images: [] }, apply_both_scanners: true, scanner: null,
      justification: 'x', vex_justification: null, expiry: null, created_by: by,
      created_at: '2026-10-18T10:00:00Z',
    })
    vi.mocked(approvalListApiV1DecisionsApprovalsGet).mockResolvedValue(
      ok({ approvals: [row('1', 'ann'), row('2', 'bob')], total: 2, facets: {} }) as never,
    )
    const w = await mountAt(ApprovalsView, { approver: 'ann' })
    await w.find('[aria-label="Filter to Approver bob"]').trigger('click')
    await flushPromises()
    expect(lastQuery(approvalListApiV1DecisionsApprovalsGet).created_by).toEqual(['ann', 'bob'])
  })
})

describe('Audit log: Entity, Action and User take several values', () => {
  it('sends every picked value, in the exclude form too', async () => {
    await mountAt(AuditTrailView, { entity: 'finding,decision', action: '!login,!logout', actor: 'ann,bob' })
    for (const fn of [readAuditLogApiV1AuditGet, auditFacetsApiV1AuditFacetsGet]) {
      const q = lastQuery(fn)
      expect(q.entity_type).toEqual(['finding', 'decision'])
      expect(q.exclude_action).toEqual(['login', 'logout'])
      expect(q.actor).toEqual(['ann', 'bob'])
    }
  })

  it('a link with 40 users keeps 32 in the rows and the counts', async () => {
    const w = await mountAt(AuditTrailView, { actor: forty.join(',') })
    expect(lastQuery(readAuditLogApiV1AuditGet).actor).toEqual(forty.slice(0, 32))
    expect(lastQuery(auditFacetsApiV1AuditFacetsGet).actor).toEqual(forty.slice(0, 32))
    expect(w.find('.facet-cap[role="status"]').text()).toBe('A filter takes at most 32 values.')
    expect(w.findComponent(FilterBar).props('maxValues')).toBe(32)
  })
})

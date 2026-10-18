/**
 * The toast after a revoke on the Approval list (issue 911): the server makes the findings Open
 * in the revoke request itself, so the toast says they are Open again, not that they will be.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'
import ApprovalsView from '@/views/ApprovalsView.vue'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    approvalListApiV1DecisionsApprovalsGet: vi.fn<() => Promise<unknown>>(),
    revokeApiV1DecisionsDecisionIdRevokePost: vi.fn<() => Promise<unknown>>(),
    // the Decision activity chart on the page
    auditFacetsApiV1AuditFacetsGet: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import {
  approvalListApiV1DecisionsApprovalsGet,
  auditFacetsApiV1AuditFacetsGet,
  revokeApiV1DecisionsDecisionIdRevokePost,
} from '@/api/generated'

const CLUSTER = 'c-k3d-0001'
const approval = {
  decision_id: 'd-1',
  cve_id: 'CVE-2026-0001',
  type: 'risk_accepted',
  scope: { namespaces: ['shop'], images: [] },
  apply_both_scanners: true,
  scanner: null,
  justification: 'No fix yet.',
  vex_justification: null,
  expiry: null,
  created_by: 'lead',
  created_at: '2026-10-18T10:00:00Z',
}

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      // each row links to its findings
      { path: '/findings', name: 'findings', component: { template: '<div />' } },
      { path: '/:any(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  const w = mount(ApprovalsView, { global: { plugins: [router, [PrimeVue, { unstyled: true }]] } })
  await flushPromises()
  return w
}

const revokeButton = (w: Awaited<ReturnType<typeof mountView>>) =>
  w.findAll('button').find((b) => /Revoke|Confirm revoke/.test(b.text()))!

describe('ApprovalsView revoke toast (issue 911)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    const clusters = useClusterStore()
    clusters.clusters = [{ cluster_id: CLUSTER, cluster_name: 'k3d' }] as never
    clusters.selectedId = CLUSTER
    clusters.loaded = true
    vi.mocked(approvalListApiV1DecisionsApprovalsGet).mockResolvedValue(
      ok({ approvals: [approval], total: 1, facets: {} }) as never,
    )
    vi.mocked(revokeApiV1DecisionsDecisionIdRevokePost).mockResolvedValue(ok({}) as never)
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValue(ok({ facets: {}, activity: [] }) as never)
  })

  it('after Confirm revoke, the toast says the findings are Open again', async () => {
    const w = await mountView()
    await revokeButton(w).trigger('click') // arms
    await revokeButton(w).trigger('click') // confirms
    await flushPromises()

    expect(revokeApiV1DecisionsDecisionIdRevokePost).toHaveBeenCalledOnce()
    const messages = useToastStore().toasts.map((t) => t.message)
    expect(messages).toEqual(['Acceptance revoked. Its findings are Open again.'])
  })
})

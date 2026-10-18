/**
 * The finding page after a decision (issue 910): a risk acceptance or a revoke changes the state
 * of the finding on the server at once, so the page reads the finding again and shows the new
 * state, not the one it loaded first.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import DecisionsCard from '@/components/triage/DecisionsCard.vue'
import RiskAcceptDialog from '@/components/triage/RiskAcceptDialog.vue'
import TriagePanel from '@/components/triage/TriagePanel.vue'
import { useClusterStore } from '@/stores/cluster'
import FindingDetailView from '@/views/FindingDetailView.vue'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    searchFindingsApiV1FindingsGet: vi.fn<() => Promise<unknown>>(),
    listDecisionsApiV1DecisionsGet: vi.fn<() => Promise<unknown>>(),
    readAuditLogApiV1AuditGet: vi.fn<() => Promise<unknown>>(),
    revokeApiV1DecisionsDecisionIdRevokePost: vi.fn<() => Promise<unknown>>(),
    closeCursorApiV1CursorsClosePost: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import {
  closeCursorApiV1CursorsClosePost,
  listDecisionsApiV1DecisionsGet,
  readAuditLogApiV1AuditGet,
  revokeApiV1DecisionsDecisionIdRevokePost,
  searchFindingsApiV1FindingsGet,
} from '@/api/generated'

const searchMock = vi.mocked(searchFindingsApiV1FindingsGet)

const row = (scanner: string, state: string) =>
  ({
    finding_key: `fk-${scanner}`,
    cve_id: 'CVE-2026-0001',
    scanner,
    severity: 'High',
    severity_canonical: 'high',
    state,
    package_name: 'openssl',
    installed_version: '3.0.1',
    fixed_version: null,
    fixable: false,
    namespaces: ['shop'],
    epss: null,
    kev: false,
    disagree: false,
    image_repo: 'registry.example/auth',
    image_digest: 'sha256:abc',
    tag: '5.2.4',
  }) as never

/** The server's answer for the pair read follows `state`; the occurrence read is empty. */
let state = 'open'
const pairReads = () =>
  searchMock.mock.calls.filter((c) => (c[0] as { query: { image_digest?: string } }).query.image_digest)

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/findings/:cveId', name: 'finding', component: FindingDetailView },
    { path: '/findings', name: 'findings', component: { template: '<div />' } },
  ],
})

async function mountPage() {
  await router.push('/findings/CVE-2026-0001?digest=sha256:abc')
  const w = mount(FindingDetailView, { global: { plugins: [router] } })
  await flushPromises()
  return w
}

describe('FindingDetailView after a decision (issue 910)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    state = 'open'
    useClusterStore().clusters = [{ cluster_id: 'c-1', cluster_name: 'c-1' }] as never
    useClusterStore().selectedId = 'c-1'
    searchMock.mockImplementation((async (opts: { query: { image_digest?: string } }) =>
      opts.query.image_digest
        ? ok({ data: [row('trivy', state), row('grype', state)], total: 2 })
        : ok({ data: [], total: 0 })) as never)
    vi.mocked(listDecisionsApiV1DecisionsGet).mockResolvedValue(ok({ decisions: [] }) as never)
    vi.mocked(readAuditLogApiV1AuditGet).mockResolvedValue(ok({ data: [] }) as never)
    vi.mocked(closeCursorApiV1CursorsClosePost).mockResolvedValue(ok({}) as never)
    vi.mocked(revokeApiV1DecisionsDecisionIdRevokePost).mockResolvedValue(ok({}) as never)
  })

  it('a new risk acceptance: the page reads the finding again and shows Risk accepted', async () => {
    const w = await mountPage()
    expect(w.findComponent(TriagePanel).props('finding')).toMatchObject({ state: 'open' })
    const before = pairReads().length

    w.findComponent(TriagePanel).vm.$emit('riskAccept')
    await flushPromises()
    state = 'risk_accepted' // the server reprojected in the create request
    w.findComponent(RiskAcceptDialog).vm.$emit('created')
    await flushPromises()

    expect(pairReads().length).toBe(before + 1)
    expect(w.findComponent(TriagePanel).props('finding')).toMatchObject({ state: 'risk_accepted' })
  })

  it('a revoke: the page reads the finding again and shows Open', async () => {
    state = 'risk_accepted'
    const w = await mountPage()
    expect(w.findComponent(TriagePanel).props('finding')).toMatchObject({ state: 'risk_accepted' })
    const before = pairReads().length

    state = 'open' // the server reprojected in the revoke request
    w.findComponent(DecisionsCard).vm.$emit('revoke', 'd-1')
    await flushPromises()

    expect(pairReads().length).toBe(before + 1)
    expect(w.findComponent(TriagePanel).props('finding')).toMatchObject({ state: 'open' })
  })

  it('a refused revoke: the page does not read the finding again', async () => {
    vi.mocked(revokeApiV1DecisionsDecisionIdRevokePost).mockResolvedValue({
      data: undefined,
      response: { ok: false, status: 403 },
    } as never)
    const w = await mountPage()
    const before = pairReads().length

    w.findComponent(DecisionsCard).vm.$emit('revoke', 'd-1')
    await flushPromises()

    expect(pairReads().length).toBe(before)
  })
})

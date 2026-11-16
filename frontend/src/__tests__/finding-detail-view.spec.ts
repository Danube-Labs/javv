/**
 * The finding page after a decision (issue 910): a risk acceptance or a revoke changes the state
 * of the finding on the server at once, so the page reads the finding again and shows the new
 * state, not the one it loaded first.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import AffectedCard from '@/components/finding/AffectedCard.vue'
import DetailHead from '@/components/finding/DetailHead.vue'
import DecisionsCard from '@/components/triage/DecisionsCard.vue'
import RiskAcceptDialog from '@/components/triage/RiskAcceptDialog.vue'
import TriagePanel from '@/components/triage/TriagePanel.vue'
import { useAuthStore } from '@/stores/auth'
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
    triageApiV1FindingsFindingKeyTriagePatch: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import {
  closeCursorApiV1CursorsClosePost,
  listDecisionsApiV1DecisionsGet,
  readAuditLogApiV1AuditGet,
  revokeApiV1DecisionsDecisionIdRevokePost,
  searchFindingsApiV1FindingsGet,
  triageApiV1FindingsFindingKeyTriagePatch,
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
        ? ok({ data: [row('trivy', state), row('grype', state)], total: { value: 2, relation: 'eq' } })
        : ok({ data: [], total: { value: 0, relation: 'eq' } })) as never)
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

  it('the read of Affected components asks for the paths, the read of the finding does not (issue 1077)', async () => {
    await mountPage()
    const occ = searchMock.mock.calls
      .map((c) => (c[0] as { query: Record<string, unknown> }).query)
      .filter((q) => !q.image_digest)
    expect(occ.length).toBeGreaterThan(0)
    for (const q of occ) expect(q).toMatchObject({ cve_id: ['CVE-2026-0001'], locations: true })
    for (const c of pairReads()) expect((c[0] as { query: Record<string, unknown> }).query.locations).toBeUndefined()
  })

  it('the head band, the evidence and the Triage cell share the first row, the cards follow at full width (issue 1205)', async () => {
    const w = await mountPage()
    const row = w.find('.head-row')
    expect(row.find('.detail-head').exists()).toBe(true)
    expect(row.text()).toContain('Per-scanner evidence')
    expect(row.find('aside.triage').exists()).toBe(true)
    // three panels, in this order: the head band, the evidence, the Triage cell (operator, 2026-11-16)
    expect([...row.element.children].map((c) => c.classList[0])).toEqual(['detail-head', 'card', 'triage'])
    const titles = ['Per-scanner evidence', 'Affected components', 'Decisions on this vulnerability', 'Activity on this finding']
    const order = w
      .findAll('h2')
      .map((h) => titles.find((t) => h.text().startsWith(t)))
      .filter(Boolean)
    expect(order).toEqual(titles)
    const pair = w.find('.card-pair')
    expect(pair.text()).toContain('Decisions on this vulnerability')
    expect(pair.text()).toContain('Activity on this finding')
    expect(pair.text()).not.toContain('Affected components')
  })

  it.each([
    [409, 'Another person changed this finding. Load the page again. Then save your change again.'],
    [422, 'JAVV did not accept this change of state. Load the page again. Then try again.'],
    [500, 'JAVV did not save the change. The backend did not answer, or it sent an error. Try again.'],
  ])('a save that fails with %i: the cell shows the error line (strict STE)', async (status, line) => {
    vi.mocked(triageApiV1FindingsFindingKeyTriagePatch).mockResolvedValue({
      data: undefined,
      response: { ok: false, status },
    } as never)
    const w = await mountPage()
    w.findComponent(TriagePanel).vm.$emit('save', { state: 'acknowledged' })
    await flushPromises()
    expect(w.find('aside.triage [role="alert"]').text()).toBe(line)
  })

  it.each([
    [true, true],
    [false, false],
  ])('a save from the cell that succeeds (%s): the draft empties only then (review round 1)', async (ok, emptied) => {
    useAuthStore().user = { username: 'lead', role: 'x', capabilities: ['can_triage'], must_change: false } as never
    vi.mocked(triageApiV1FindingsFindingKeyTriagePatch).mockResolvedValue(
      (ok
        ? { data: { finding: row('trivy', 'acknowledged') }, response: { ok: true, status: 200 } }
        : { data: undefined, response: { ok: false, status: 409 } }) as never,
    )
    const w = await mountPage()
    const cellSave = () => w.find('aside.triage .ui-btn--primary')
    await w.findAll('aside.triage .state-opt').find((b) => b.text() === 'Acknowledge')!.trigger('click')
    await w.findAll('aside.triage button').find((b) => b.text() === 'Note and more…')!.trigger('click')
    await flushPromises()
    await w.find('#triage-notes').setValue('checked the image')
    expect(cellSave().attributes('disabled')).toBeUndefined()
    await cellSave().trigger('click')
    await flushPromises()
    expect(cellSave().attributes('disabled') !== undefined).toBe(emptied)
  })

  it('more occurrences than the read holds: the card says so (review F3, the server sends total as an object)', async () => {
    searchMock.mockImplementation((async (opts: { query: { image_digest?: string } }) =>
      opts.query.image_digest
        ? ok({ data: [row('trivy', state)], total: { value: 1, relation: 'eq' } })
        : ok({ data: [row('trivy', state)], total: { value: 300, relation: 'eq' } })) as never)
    const w = await mountPage()
    expect(w.text()).toContain('To see all of them, search for the vulnerability ID on the Findings page.')
  })
})

describe('FindingDetailView, the Affected card (issue 1205, group 3)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    searchMock.mockResolvedValue(ok({ data: [row('trivy', 'open')], total: { value: 1, relation: 'eq' } }) as never)
    vi.mocked(listDecisionsApiV1DecisionsGet).mockResolvedValue(ok({ decisions: [] }) as never)
    vi.mocked(readAuditLogApiV1AuditGet).mockResolvedValue(ok({ data: [] }) as never)
    vi.mocked(closeCursorApiV1CursorsClosePost).mockResolvedValue(ok({}) as never)
  })

  it('gets the ID of the page and the name of the selected cluster', async () => {
    useClusterStore().clusters = [{ cluster_id: 'c-1', cluster_name: 'alpha' }] as never
    useClusterStore().selectedId = 'c-1'
    const w = await mountPage()
    expect(w.findComponent(AffectedCard).props()).toMatchObject({ cveId: 'CVE-2026-0001', clusterName: 'alpha' })
  })

  it('gets the cluster id when the cluster list does not have the selected cluster', async () => {
    useClusterStore().clusters = [] as never
    useClusterStore().selectedId = 'c-1'
    const w = await mountPage()
    expect(w.findComponent(AffectedCard).props('clusterName')).toBe('c-1')
  })
})

describe('FindingDetailView, the reads of the finding and its packages (issue 1227)', () => {
  type Q = { query: { image_digest?: string; package_name?: string[]; size?: number } }
  const pkgRow = (name: string, scanner: string, version = '10.2.1-6') =>
    ({ ...(row(scanner, 'open') as object), finding_key: `fk-${name}-${scanner}`, package_name: name, installed_version: version }) as never
  /** 18 packages on the image; the read of one package answers with that package only */
  const names = Array.from({ length: 18 }, (_, i) => `pkg-${String(i).padStart(2, '0')}`)
  let listAnswer: () => unknown
  const listReads = () => searchMock.mock.calls.filter((c) => (c[0] as Q).query.size === 500)
  const evidenceReads = () =>
    searchMock.mock.calls.filter((c) => (c[0] as Q).query.image_digest && (c[0] as Q).query.size !== 500)

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useClusterStore().clusters = [{ cluster_id: 'c-1', cluster_name: 'alpha' }] as never
    useClusterStore().selectedId = 'c-1'
    const all = names.flatMap((n) => [pkgRow(n, 'trivy'), pkgRow(n, 'grype')])
    listAnswer = () => ok({ data: all, total: { value: all.length, relation: 'eq' } })
    searchMock.mockImplementation((async (opts: Q) => {
      if (opts.query.size === 500) return listAnswer()
      if (opts.query.image_digest) {
        const want = opts.query.package_name?.[0]
        const data = want ? all.filter((r: { package_name: string }) => r.package_name === want) : all.slice(0, 10)
        return ok({ data, total: { value: data.length, relation: 'eq' } })
      }
      return ok({ data: [], total: { value: 0, relation: 'eq' } })
    }) as never)
    vi.mocked(listDecisionsApiV1DecisionsGet).mockResolvedValue(ok({ decisions: [] }) as never)
    vi.mocked(readAuditLogApiV1AuditGet).mockResolvedValue(ok({ data: [] }) as never)
    vi.mocked(closeCursorApiV1CursorsClosePost).mockResolvedValue(ok({}) as never)
  })

  async function mountAt(url: string) {
    await router.push(url)
    const w = mount(FindingDetailView, { global: { plugins: [router] } })
    await flushPromises()
    return w
  }

  it('the read of the finding asks for the package of the link, so a package past the first 10 shows', async () => {
    const w = await mountAt('/findings/CVE-2026-0001?digest=sha256:abc&pkg=pkg-15&ver=10.2.1-6')
    expect((evidenceReads().at(-1)![0] as Q).query.package_name).toEqual(['pkg-15'])
    expect(w.findComponent(TriagePanel).props('finding')).toMatchObject({ package_name: 'pkg-15' })
  })

  it('a second read lists each package of the CVE on the image, with no package filter', async () => {
    const w = await mountAt('/findings/CVE-2026-0001?digest=sha256:abc&pkg=pkg-15&ver=10.2.1-6')
    expect(listReads()).toHaveLength(1)
    const q = (listReads()[0]![0] as Q).query
    expect(q).toMatchObject({ cve_id: ['CVE-2026-0001'], image_digest: 'sha256:abc', size: 500 })
    expect(q.package_name).toBeUndefined()
    expect(w.findComponent(DetailHead).props('packages')).toHaveLength(18)
    expect(w.findComponent(DetailHead).props('packagesCut')).toBe(false)
  })

  it('more findings than the list read holds: the head band knows the list is cut', async () => {
    listAnswer = () => ok({ data: [pkgRow('pkg-00', 'trivy')], total: { value: 600, relation: 'eq' } })
    const w = await mountAt('/findings/CVE-2026-0001?digest=sha256:abc&pkg=pkg-00&ver=10.2.1-6')
    expect(w.findComponent(DetailHead).props('packagesCut')).toBe(true)
  })

  it('a refused list read: no menu, and the finding still shows', async () => {
    listAnswer = () => ({ data: undefined, response: { ok: false, status: 500 } })
    const w = await mountAt('/findings/CVE-2026-0001?digest=sha256:abc&pkg=pkg-03&ver=10.2.1-6')
    expect(w.findComponent(DetailHead).props('packages')).toEqual([])
    expect(w.findComponent(TriagePanel).props('finding')).toMatchObject({ package_name: 'pkg-03' })
  })

  it('a link whose version no row has: the page names the package and version it looked for, with no Triage cell', async () => {
    const w = await mountAt('/findings/CVE-2026-0001?digest=sha256:abc&pkg=pkg-03&ver=9.9.9')
    expect(w.findComponent(TriagePanel).exists()).toBe(false)
    expect(w.find('.not-found p').text().replace(/\s+/g, ' ')).toBe(
      'This image has no finding of CVE-2026-0001 in pkg-03 9.9.9 at the selected time. A newer scan may no longer report it. Or the selected time range may end before a scan found it.',
    )
  })

  it('a link with a package and no version: the line names the package alone', async () => {
    searchMock.mockResolvedValue(ok({ data: [], total: { value: 0, relation: 'eq' } }) as never)
    const w = await mountAt('/findings/CVE-2026-0001?digest=sha256:abc&pkg=pkg-99')
    expect(w.find('.not-found p').text().replace(/\s+/g, ' ')).toContain('no finding of CVE-2026-0001 in pkg-99 at the selected time.')
  })

  it('a link with no package keeps the line of the CVE on the image', async () => {
    searchMock.mockResolvedValue(ok({ data: [], total: { value: 0, relation: 'eq' } }) as never)
    const w = await mountAt('/findings/CVE-2026-0001?digest=sha256:abc')
    expect(w.find('.not-found p').text().replace(/\s+/g, ' ')).toContain('No current finding for this vulnerability on this image.')
  })
})

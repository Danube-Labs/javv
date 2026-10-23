/**
 * A refused read is not an empty answer (issue 817, finding 5). A 429 on the findings search showed
 * the right alert, but also "0 findings" and "No findings yet" under it, while the facets counted
 * 508. Here every SDK call is refused: each grid shows its failure copy, and neither its head count
 * nor its table claims there is nothing.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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

import {
  approvalListApiV1DecisionsApprovalsGet,
  auditFacetsApiV1AuditFacetsGet,
  contributorsApiV1ContributorsGet,
  listViewsApiV1ViewsGet,
  scannerProvenanceApiV1ScannersProvenanceGet,
  facetFindingsApiV1FindingsFacetsGet,
  listDecisionsApiV1DecisionsGet,
  readAuditLogApiV1AuditGet as readActivity,
  readAuditLogApiV1AuditGet,
  searchFindingsApiV1FindingsGet,
} from '@/api/generated'
import AuditTable from '@/components/audit/AuditTable.vue'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { FAILURE_COPY } from '@/findings/failureCopy'
import { APPROVAL_FIELDS } from '@/approvals/fields.config'
import { AUDIT_FIELDS } from '@/audit/fields.config'
import { useAuditStore } from '@/stores/audit'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { makeFiltersStore } from '@/stores/filters'
import { useFindingsStore } from '@/stores/findings'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'
import ApprovalsView from '@/views/ApprovalsView.vue'
import AuditTrailView from '@/views/AuditTrailView.vue'
import ContributorsView from '@/views/ContributorsView.vue'
import SavedViewsView from '@/views/SavedViewsView.vue'
import ScannerStatusView from '@/views/ScannerStatusView.vue'
import FindingDetailView from '@/views/FindingDetailView.vue'
import FindingsView from '@/views/FindingsView.vue'
import ImagesView from '@/views/ImagesView.vue'

const CLUSTER = 'c-k3d-0001'

async function mountRouted(component: Component, props: Record<string, unknown> = {}, path = '/') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/findings/:cveId', name: 'finding', component: { template: '<div />' } },
      { path: '/:any(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  return mount(component, { props, global: { plugins: [router, [PrimeVue, { unstyled: true }]], stubs: { EChart: true } } })
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
    ['Audit log', AuditTrailView, 'The search backend is busy.', /(?<!\d)0 events/, ['No journaled activity']],
    // "0 contributors"
    ['Contributors', ContributorsView, 'The search backend is busy.', /(?<!\d)0 contributors/, []],
    // "0 standing acceptances"
    ['Approvals', ApprovalsView, 'The search backend is busy.', /(?<!\d)0 standing acceptances/, []],
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

const refusedWith = (status: number) => ({
  error: { title: 'refused' },
  request: {},
  response: { ok: false, status },
})
const findingsPage = (cve: string, total: number, next: string | null) => ({
  data: {
    data: [
      {
        finding_key: `k-${cve}`,
        cve_id: cve,
        scanner: 'trivy',
        severity: 'low',
        severity_canonical: 'low',
        image_repo: 'repo',
        tag: '1',
        package_name: 'pkg',
        installed_version: '1.0',
        fixed_version: null,
        fixable: false,
        epss: null,
        kev: false,
        ptype: null,
        state: 'open',
        overdue: false,
        due_at: null,
      },
    ],
    total: { value: total, relation: 'eq' },
    next_cursor: next,
  },
  request: {},
  response: { ok: true, status: 200 },
})

describe('Findings: a refused read never leaves the last answer on screen (issue 833)', () => {
  const search = () => vi.mocked(searchFindingsApiV1FindingsGet)
  const filters = () => makeFiltersStore('findings-filters', FINDINGS_FIELDS)()

  async function mountWithFirstPage(next: string | null = 'cur-2') {
    search().mockResolvedValueOnce(findingsPage('CVE-2026-0001', 435, next) as never)
    const w = await mountRouted(FindingsView as Component)
    await flushPromises()
    expect(w.text()).toContain('CVE-2026-0001')
    return w
  }

  it('a refused read after a good one clears the rows and the count', async () => {
    const w = await mountWithFirstPage()
    search().mockResolvedValueOnce(refusedWith(429) as never)
    filters().toggle('severity', 'critical')
    await flushPromises()
    const text = w.text()
    expect(text).toContain('The search backend is busy.')
    expect(text).toContain('Findings could not be loaded.')
    expect(text).not.toContain('CVE-2026-0001')
    expect(text).not.toMatch(/435/)
  })

  it.each([
    [503, 'Findings unavailable. Check the backend connection.'],
    [410, 'These results expired. Reload the page to start again.'],
  ])('a %s on page 2 stays on page 2, says so, and keeps Prev', async (status, copy) => {
    const w = await mountWithFirstPage()
    search().mockResolvedValueOnce(refusedWith(status) as never)
    useFindingsStore().goNext()
    await flushPromises()
    const text = w.text()
    expect(text).toContain(copy)
    expect(text).toContain('Findings could not be loaded.')
    expect(text).toContain('Showing 26–50 of 435')
    // the total is still this query's, from page 1 (operator ruling 2026-10-13)
    expect(w.find('.head-stat').text()).toBe('435 findings')
    const prev = w.findAll('.pager-btn').find((b) => b.text() === 'Prev')!
    expect(prev.attributes('disabled')).toBeUndefined()
  })

  it('a slow answer for an older filter does not replace a newer refusal', async () => {
    const w = await mountWithFirstPage()
    let answerOld: (v: unknown) => void = () => {}
    search().mockImplementationOnce(() => new Promise((resolve) => (answerOld = resolve)) as never)
    filters().toggle('severity', 'high')
    await flushPromises()
    search().mockResolvedValueOnce(refusedWith(429) as never)
    filters().toggle('severity', 'critical')
    await flushPromises()
    answerOld(findingsPage('CVE-2026-0002', 12, null))
    await flushPromises()
    const text = w.text()
    expect(text).toContain('The search backend is busy.')
    expect(text).not.toContain('CVE-2026-0002')
  })
})

describe('Findings: only the filter counts refused (issue 833, F9 under G2)', () => {
  const facetsOk = {
    data: { facets: { severity: [{ key: 'low', count: 435, by_scanner: { trivy: 435 } }] } },
    request: {},
    response: { ok: true, status: 200 },
  }

  it.each([
    [429, 'Filter counts could not be loaded. The search backend is busy. Try again in a few seconds.'],
    [503, 'Filter counts could not be loaded. Check the backend connection.'],
  ])('a %s: the rows stay, the alert names the counts, the rail shows "-"', async (status, copy) => {
    vi.mocked(facetFindingsApiV1FindingsFacetsGet)
      .mockResolvedValueOnce(facetsOk as never)
      .mockResolvedValueOnce(refusedWith(status) as never)
    vi.mocked(searchFindingsApiV1FindingsGet)
      .mockResolvedValueOnce(findingsPage('CVE-2026-0001', 435, null) as never)
      .mockResolvedValueOnce(findingsPage('CVE-2026-0003', 7, null) as never)
    const w = await mountRouted(FindingsView as Component)
    await flushPromises()
    expect(w.find('.facet-count').text()).toBe('435')
    makeFiltersStore('findings-filters', FINDINGS_FIELDS)().toggle('severity', 'low')
    await flushPromises()
    expect(w.find('.load-error').text()).toBe(copy)
    expect(w.text()).toContain('CVE-2026-0003')
    expect(w.findAll('.facet-count').map((c) => c.text())).toEqual(['-'])
  })
  it('a slow counts answer for an older filter does not replace a newer refusal', async () => {
    let answerOld: (v: unknown) => void = () => {}
    vi.mocked(facetFindingsApiV1FindingsFacetsGet)
      .mockResolvedValueOnce(facetsOk as never)
      .mockImplementationOnce(() => new Promise((resolve) => (answerOld = resolve)) as never)
      .mockResolvedValueOnce(refusedWith(503) as never)
    const page = findingsPage('CVE-2026-0001', 435, null) as never
    vi.mocked(searchFindingsApiV1FindingsGet)
      .mockResolvedValueOnce(page)
      .mockResolvedValueOnce(page)
      .mockResolvedValueOnce(page)
    const w = await mountRouted(FindingsView as Component)
    await flushPromises()
    const f = makeFiltersStore('findings-filters', FINDINGS_FIELDS)()
    f.toggle('severity', 'high')
    await flushPromises()
    f.toggle('severity', 'low')
    await flushPromises()
    answerOld(facetsOk)
    await flushPromises()
    expect(w.find('.load-error').text()).toContain('Filter counts could not be loaded.')
    expect(w.findAll('.facet-count').map((c) => c.text())).toEqual(['-'])
  })
})

const auditPage = (actor: string, total: number, next: string | null) => ({
  data: {
    data: [
      {
        event_id: `e-${actor}`,
        '@timestamp': '2026-10-12T10:00:00Z',
        actor,
        action: 'triage',
        entity_type: 'finding',
        entity_id: 'f-1',
      },
    ],
    total: { value: total, relation: 'eq' },
    next_cursor: next,
  },
  request: {},
  response: { ok: true, status: 200 },
})

describe('Audit log: the same rules as Findings (issue 833)', () => {
  const read = () => vi.mocked(readAuditLogApiV1AuditGet)
  const filters = () => makeFiltersStore('audit-filters', AUDIT_FIELDS)()
  const ROWS_DOWN = 'Audit log unavailable. Check the backend connection, then retry.'

  async function mountWithFirstPage() {
    read().mockResolvedValueOnce(auditPage('alice-old', 60, 'cur-2') as never)
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValueOnce({
      data: { facets: { entity_type: [{ key: 'finding', count: 60 }] } },
      request: {},
      response: { ok: true, status: 200 },
    } as never)
    const w = await mountRouted(AuditTrailView as Component)
    await flushPromises()
    expect(w.text()).toContain('alice-old')
    return w
  }

  it('G3: the count is "-" until the first read answers', async () => {
    read().mockImplementationOnce(() => new Promise(() => {}) as never)
    const w = await mountRouted(AuditTrailView as Component)
    await flushPromises()
    expect(w.find('.head-stat').text()).toBe('- events')
  })

  it('F1 and G2: a refused read after a good one clears the rows and says busy', async () => {
    const w = await mountWithFirstPage()
    read().mockResolvedValueOnce(refusedWith(429) as never)
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValueOnce(refusedWith(429) as never)
    filters().toggle('action', 'triage')
    await flushPromises()
    const text = w.text()
    expect(w.find('.load-error').text()).toBe('The search backend is busy. Try again in a few seconds.')
    expect(text).toContain('Events could not be loaded.')
    expect(text).not.toContain('alice-old')
    expect(w.find('.head-stat').text()).toBe('- events')
  })

  it.each([
    [503, ROWS_DOWN],
    [410, 'These results expired. Reload the page to start again.'],
  ])('G1: a %s on page 2 stays on page 2 and keeps Prev', async (status, copy) => {
    const w = await mountWithFirstPage()
    read().mockResolvedValueOnce(refusedWith(status) as never)
    useAuditStore().goNext()
    await flushPromises()
    expect(w.find('.load-error').text()).toBe(copy)
    expect(w.text()).toContain('Showing 26–50 of 60')
    expect(w.find('.head-stat').text()).toBe('60 events')
    const prev = w.findAll('.pager-btn').find((b) => b.text() === 'Prev')!
    expect(prev.attributes('disabled')).toBeUndefined()
  })

  it('F9 ruled for this rail too: only the counts refused leaves the rows', async () => {
    const w = await mountWithFirstPage()
    read().mockResolvedValueOnce(auditPage('bob-new', 3, null) as never)
    vi.mocked(auditFacetsApiV1AuditFacetsGet).mockResolvedValueOnce(refusedWith(503) as never)
    filters().toggle('action', 'triage')
    await flushPromises()
    expect(w.find('.load-error').text()).toBe('Filter counts could not be loaded. Check the backend connection.')
    expect(w.text()).toContain('bob-new')
    expect(w.findAll('.facet-count').map((c) => c.text())).toContain('-')
  })

  it('F3: a slow answer for an older filter does not replace a newer refusal', async () => {
    const w = await mountWithFirstPage()
    let answerOld: (v: unknown) => void = () => {}
    read().mockImplementationOnce(() => new Promise((resolve) => (answerOld = resolve)) as never)
    filters().toggle('action', 'triage')
    await flushPromises()
    read().mockResolvedValueOnce(refusedWith(503) as never)
    filters().toggle('actor', 'carol')
    await flushPromises()
    answerOld(auditPage('dave-stale', 2, null))
    await flushPromises()
    expect(w.text()).not.toContain('dave-stale')
    expect(w.text()).toContain('Events could not be loaded.')
  })
})

describe('Contributors and Approvals: the reason, and the newest answer (issue 833, G2 and F3)', () => {
  const ok = (data: unknown) => ({ data, request: {}, response: { ok: true, status: 200 } })
  const contributorsOk = ok({ leaderboard: [], handled_over_time: [], totals: null })
  const approvalsOk = ok({ approvals: [], total: 5, facets: {} })

  it.each([
    [429, 'The search backend is busy. Try again in a few seconds.'],
    [503, 'Contributors unavailable. Check the backend connection.'],
  ])('Contributors, a %s', async (status, copy) => {
    vi.mocked(contributorsApiV1ContributorsGet).mockResolvedValueOnce(refusedWith(status) as never)
    const w = await mountRouted(ContributorsView as Component)
    await flushPromises()
    expect(w.find('.load-error').text()).toBe(copy)
  })

  it.each([
    [429, 'The search backend is busy. Try again in a few seconds.'],
    [503, 'Could not load the queue. Check the backend connection.'],
  ])('Approvals, a %s', async (status, copy) => {
    vi.mocked(approvalListApiV1DecisionsApprovalsGet).mockResolvedValueOnce(refusedWith(status) as never)
    const w = await mountRouted(ApprovalsView as Component)
    await flushPromises()
    expect(w.find('.load-error').text()).toBe(copy)
  })

  it('Approvals: a refused read leaves the rail values with "-" counts (operator ruling 2026-10-13)', async () => {
    vi.mocked(approvalListApiV1DecisionsApprovalsGet)
      .mockResolvedValueOnce(ok({ approvals: [], total: 5, facets: { status: [{ key: 'active', count: 5 }] } }) as never)
      .mockResolvedValueOnce(refusedWith(503) as never)
    const w = await mountRouted(ApprovalsView as Component)
    await flushPromises()
    expect(w.findAll('.facet-count').map((c) => c.text())).toContain('5')
    makeFiltersStore('approvals-filters', APPROVAL_FIELDS)().toggle('scanner', 'trivy')
    await flushPromises()
    expect(w.find('.load-error').exists()).toBe(true)
    const counts = w.findAll('.facet-count').map((c) => c.text())
    expect(counts).not.toContain('5')
    expect(counts).toContain('-')
  })

  it('Contributors: a slow answer for an older window does not replace a newer refusal', async () => {
    let answerOld: (v: unknown) => void = () => {}
    vi.mocked(contributorsApiV1ContributorsGet)
      .mockImplementationOnce(() => new Promise((resolve) => (answerOld = resolve)) as never)
      .mockResolvedValueOnce(refusedWith(503) as never)
    const w = await mountRouted(ContributorsView as Component)
    await flushPromises()
    useTimeTravelStore().setWindow(7)
    await flushPromises()
    answerOld(contributorsOk)
    await flushPromises()
    expect(w.find('.head-stat').text()).toBe('- contributors')
  })

  it('Approvals: a slow answer for an older filter does not replace a newer refusal', async () => {
    let answerOld: (v: unknown) => void = () => {}
    vi.mocked(approvalListApiV1DecisionsApprovalsGet)
      .mockImplementationOnce(() => new Promise((resolve) => (answerOld = resolve)) as never)
      .mockResolvedValueOnce(refusedWith(503) as never)
    const w = await mountRouted(ApprovalsView as Component)
    await flushPromises()
    makeFiltersStore('approvals-filters', APPROVAL_FIELDS)().toggle('scanner', 'trivy')
    await flushPromises()
    answerOld(approvalsOk)
    await flushPromises()
    expect(w.find('.load-error').exists()).toBe(true)
    expect(w.find('.head-stat').text()).not.toMatch(/5/)
  })
})

describe('Finding detail: a refused card read says so (issue 833, F2)', () => {
  const DETAIL = '/findings/CVE-2026-0001?digest=sha256:abc&scanner=trivy&pkg=pkg&ver=1.0'
  const ok = (data: unknown) => ({ data, request: {}, response: { ok: true, status: 200 } })

  async function mountDetail(path = DETAIL) {
    useAuthStore().user = { username: 'admin', capabilities: ['*'] } as never
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/findings/:cveId', name: 'finding', component: FindingDetailView },
        { path: '/:any(.*)*', component: { template: '<div />' } },
      ],
    })
    await router.push(path)
    const w = mount({ template: '<router-view />' }, {
      global: { plugins: [router, [PrimeVue, { unstyled: true }]], stubs: { EChart: true } },
    })
    await flushPromises()
    return { w, router }
  }
  afterEach(() => {
    vi.mocked(searchFindingsApiV1FindingsGet).mockImplementation(async () => refusedWith(429) as never)
  })

  /** The page reads the finding itself (size 10) and its occurrences (size 200), in no fixed order. */
  function answerSearch(cve: string, occurrences: unknown) {
    vi.mocked(searchFindingsApiV1FindingsGet).mockImplementation(
      async (opts) =>
        ((opts as { query: { size: number } }).query.size === 10
          ? findingsPage(cve, 1, null)
          : occurrences) as never,
    )
  }

  it('a link with no digest says what is missing, and stops loading (issue 892)', async () => {
    const { w } = await mountDetail('/findings/CVE-2026-0001')
    expect(w.find('[aria-busy="true"]').exists()).toBe(false)
    expect(w.find('.not-found h1').text()).toBe('CVE-2026-0001')
    expect(w.text()).toContain('This link is missing the image identity. Open the finding from the grid.')
  })

  it('each card says "Could not be loaded.", the badge shows "-", New decision is off', async () => {
    answerSearch('CVE-2026-0001', refusedWith(429))
    // the activity and decisions reads keep the default refusal
    const { w } = await mountDetail()
    const text = w.text()
    expect(text).not.toContain('No occurrences returned.')
    expect(text).not.toContain('No triage actions yet.')
    expect(text).not.toContain('No decisions on this CVE yet.')
    expect(text.match(/Could not be loaded\./g)).toHaveLength(3)
    expect(w.find('.count-badge').text()).toBe('-')
    const newDecision = w.findAll('button').find((b) => b.text().includes('New decision'))!
    expect(newDecision.attributes('disabled')).toBeDefined()
  })

  it('a refused read for another CVE drops the decisions of the one before', async () => {
    const decision = { decision_id: 'd-old', type: 'risk_accepted', created_by: 'erin-old' }
    answerSearch('CVE-2026-0001', ok({ data: [], total: 0 }))
    vi.mocked(listDecisionsApiV1DecisionsGet).mockResolvedValueOnce(ok({ decisions: [decision] }) as never)
    const { w, router } = await mountDetail()
    expect(w.text()).toContain('erin-old')
    answerSearch('CVE-2026-0009', ok({ data: [], total: 0 }))
    await router.push(DETAIL.replace('CVE-2026-0001', 'CVE-2026-0009'))
    await flushPromises()
    expect(w.text()).toContain('CVE-2026-0009') // the cards are on screen, for the new CVE
    expect(w.text()).not.toContain('erin-old')
  })

  it('F3: late answers for the previous CVE never land on the next one', async () => {
    const held: ((v: unknown) => void)[] = []
    const hold = () => new Promise((resolve) => held.push(resolve)) as never
    vi.mocked(searchFindingsApiV1FindingsGet).mockImplementation(async (opts) => {
      const q = (opts as { query: { cve_id: string[]; size: number } }).query
      if (q.cve_id[0] === 'CVE-2026-0001') return q.size === 10 ? (findingsPage('CVE-2026-0001', 1, null) as never) : hold()
      return (q.size === 10 ? findingsPage('CVE-2026-0009', 1, null) : refusedWith(503)) as never
    })
    vi.mocked(listDecisionsApiV1DecisionsGet).mockImplementationOnce(hold)
    vi.mocked(readActivity).mockImplementationOnce(hold)
    const { w, router } = await mountDetail()
    await router.push(DETAIL.replace('CVE-2026-0001', 'CVE-2026-0009'))
    await flushPromises()
    const stale = { decision_id: 'd-old', type: 'risk_accepted', created_by: 'erin-old' }
    const oldOcc = { ...findingsPage('CVE-2026-0001', 1, null).data, total: 1 }
    for (const answer of held) {
      answer(ok({ data: oldOcc.data, total: 1, decisions: [stale] }))
    }
    await flushPromises()
    expect(w.text()).toContain('CVE-2026-0009')
    expect(w.text()).not.toContain('erin-old')
    expect(w.text().match(/Could not be loaded\./g)).toHaveLength(3)
  })

  it('F3: a late answer for the previous CVE never replaces the finding on screen', async () => {
    let answerOld: (v: unknown) => void = () => {}
    vi.mocked(searchFindingsApiV1FindingsGet).mockImplementation(async (opts) => {
      const q = (opts as { query: { cve_id: string[]; size: number } }).query
      if (q.size !== 10) return ok({ data: [], total: 0 }) as never
      if (q.cve_id[0] === 'CVE-2026-0001') return new Promise((resolve) => (answerOld = resolve)) as never
      return findingsPage('CVE-2026-0009', 1, null) as never
    })
    const { w, router } = await mountDetail()
    await router.push(DETAIL.replace('CVE-2026-0001', 'CVE-2026-0009'))
    await flushPromises()
    const before = w.text()
    answerOld(refusedWith(503))
    await flushPromises()
    expect(w.find('.load-error').exists()).toBe(false)
    expect(w.text()).toBe(before)
  })

  it('a busy pair read says busy, not a broken connection (G2)', async () => {
    const { w } = await mountDetail()
    expect(w.find('.load-error').text()).toBe('The search backend is busy. Try again in a few seconds.')
  })
})

describe('Scanner status and Saved views: a count that was not read is "-" (issue 833, F5)', () => {
  it.each([
    ['Scanner status', ScannerStatusView, '- scanners', 'The search backend is busy. Try again in a few seconds.'],
    ['Saved views', SavedViewsView, '- views', 'The search backend is busy. Try again in a few seconds.'],
  ])('%s, refused with a 429', async (_name, view, count, copy) => {
    const w = await mountRouted(view as Component)
    await flushPromises()
    expect(w.find('.head-stat').text()).toBe(count)
    expect(w.find('.load-error').text()).toBe(copy)
  })

  it.each([
    ['Scanner status', ScannerStatusView, scannerProvenanceApiV1ScannersProvenanceGet, '- scanners'],
    ['Saved views', SavedViewsView, listViewsApiV1ViewsGet, '- views'],
  ])('%s, before its first read answers', async (_name, view, sdk, count) => {
    vi.mocked(sdk).mockImplementationOnce(() => new Promise(() => {}) as never)
    const w = await mountRouted(view as Component)
    await flushPromises()
    expect(w.find('.head-stat').text()).toBe(count)
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

describe('Findings: Assignee with Unassigned on the screen (issue 975)', () => {
  const search = () => vi.mocked(searchFindingsApiV1FindingsGet)
  const lastQuery = () => {
    const call = search().mock.lastCall
    if (!call) throw new Error('Findings sent no read')
    return (call[0] as { query: Record<string, unknown> }).query
  }
  let original: ReturnType<ReturnType<typeof search>['getMockImplementation']>
  beforeEach(() => {
    original = search().getMockImplementation()
  })
  afterEach(() => {
    search().mockImplementation(original!)
  })

  const PAST = '2026-10-01T00:00:00.000Z'

  it.each([
    // the route refuses the pair before the past-time reader runs
    ['a link with both, at a past time', PAST, '/?assignee=bob&attr=unassigned', FAILURE_COPY.bad_filter],
    // KEV is not in the scan history, so this 422 is about the past time
    ['a filter the history does not record, at a past time', PAST, '/?attr=kev', FAILURE_COPY.past_t],
    ['the same filter now', null, '/?attr=kev', FAILURE_COPY.bad_filter],
  ])('%s: a 422 gets its own reason', async (_name, t, path, copy) => {
    useTimeTravelStore().t = t
    search().mockImplementation(async () => refusedWith(422) as never)
    const w = await mountRouted(FindingsView as Component, {}, path)
    await flushPromises()
    expect(lastQuery().as_of).toBe(t ?? undefined)
    expect(w.text()).toContain(copy)
  })

  it('the reason survives leaving Findings and coming back while the next read runs', async () => {
    useTimeTravelStore().t = PAST
    search().mockImplementation(async () => refusedWith(422) as never)
    const first = await mountRouted(FindingsView as Component, {}, '/?attr=kev')
    await flushPromises()
    first.unmount()
    search().mockImplementation(() => new Promise(() => {}) as never)
    const again = await mountRouted(FindingsView as Component, {}, '/?attr=kev')
    await flushPromises()
    expect(again.text()).toContain(FAILURE_COPY.past_t)
  })

  it('the reason stays the one of the refused read when the time changes', async () => {
    useTimeTravelStore().t = PAST
    search().mockImplementation(async () => refusedWith(422) as never)
    const w = await mountRouted(FindingsView as Component, {}, '/?attr=kev')
    await flushPromises()
    search().mockImplementation(() => new Promise(() => {}) as never)
    useTimeTravelStore().t = null
    await flushPromises()
    expect(w.text()).toContain(FAILURE_COPY.past_t)
  })

  it('Unassigned turned on in the Findings filters clears Assignee, says so, and the next read leaves Assignee out', async () => {
    search().mockImplementation(async () => findingsPage('CVE-2026-0001', 1, null) as never)
    await mountRouted(FindingsView as Component, {}, '/?assignee=bob')
    await flushPromises()
    expect(lastQuery().assignee).toEqual(['bob'])
    makeFiltersStore('findings-filters', FINDINGS_FIELDS)().toggle('attr', 'unassigned')
    await flushPromises()
    expect(lastQuery().assignee).toBeUndefined()
    expect(lastQuery().unassigned).toBe(true)
    expect(useToastStore().toasts.map((t) => t.message)).toEqual([
      "Assignee cleared. Assignee and Unassigned can't be used together.",
    ])
  })
})

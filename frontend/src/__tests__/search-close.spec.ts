/**
 * The UI closes the cursor walks it stops using (issue 832). A live findings or audit walk holds
 * one of the user's search slots until it is closed or expires, so a list the user leaves, a first
 * page a newer read replaced, or a one-shot read must close its walk, and a past-T findings walk,
 * which holds nothing, must not send a close. Leaving for a finding keeps the walk (ruling on the
 * plan), and a reload or closed tab closes what is still held, with keepalive requests.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
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

import { closeCursor, closeUnpaged, holdCursor, releaseCursor } from '@/api/cursors'
import {
  closeCursorApiV1CursorsClosePost,
  readAuditLogApiV1AuditGet,
  searchFindingsApiV1FindingsGet,
} from '@/api/generated'
import ActivityFeed from '@/components/contributors/ActivityFeed.vue'
import ImageFindingsPanel from '@/components/images/ImageFindingsPanel.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useFindingsStore } from '@/stores/findings'
import { useTimeTravelStore } from '@/stores/timeTravel'
import AuditTrailView from '@/views/AuditTrailView.vue'
import FindingDetailView from '@/views/FindingDetailView.vue'
import FindingsView from '@/views/FindingsView.vue'

const CLUSTER = 'c-k3d-0001'
const REFUSED = { error: { title: 'Too Many Requests' }, request: {}, response: { ok: false, status: 429 } }
const ok = (data: unknown) => ({ data, request: {}, response: { ok: true, status: 200 } })
const row = (key: string) => ({
  finding_key: key,
  cve_id: 'CVE-2026-0001',
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
})
const findingsPage = (next: string | null) =>
  ok({ data: [row(`k-${next}`)], total: { value: 60, relation: 'eq' }, next_cursor: next })
const auditPage = (next: string | null) =>
  ok({ data: [], total: { value: 60, relation: 'eq' }, next_cursor: next })

/** The cursors the UI asked the backend to close, in order. */
const closed = () =>
  vi.mocked(closeCursorApiV1CursorsClosePost).mock.calls.map((c) => (c[0] as { body: { cursor: string } }).body.cursor)

async function mountApp(routes: { path: string; name?: string; component: Component }[], start: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [...routes, { path: '/:any(.*)*', name: 'elsewhere', component: { template: '<div />' } }],
  })
  await router.push(start)
  const w = mount({ template: '<router-view />' }, {
    global: { plugins: [router, [PrimeVue, { unstyled: true }]], stubs: { EChart: true } },
  })
  await flushPromises()
  return { w, router }
}

const GRID_ROUTES = [
  { path: '/findings', name: 'findings', component: FindingsView },
  { path: '/audit', name: 'audit', component: AuditTrailView },
  { path: '/findings/:cveId', name: 'finding', component: { template: '<div />' } },
]

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.clusters = [{ cluster_id: CLUSTER, cluster_name: 'k3d' }] as never
  clusters.selectedId = CLUSTER
  clusters.loaded = true
  useAuthStore().user = { username: 'admin', capabilities: ['*'] } as never
  vi.mocked(closeCursorApiV1CursorsClosePost).mockReset()
  vi.mocked(closeCursorApiV1CursorsClosePost).mockResolvedValue(ok(null) as never)
  // each test reads only its own calls, with no answer left over from the one before
  for (const read of [searchFindingsApiV1FindingsGet, readAuditLogApiV1AuditGet]) {
    vi.mocked(read).mockReset()
    vi.mocked(read).mockResolvedValue(REFUSED as never)
  }
})

describe('the Findings and Audit grids', () => {
  it.each([
    ['Findings', '/findings', searchFindingsApiV1FindingsGet, findingsPage],
    ['Audit log', '/audit', readAuditLogApiV1AuditGet, auditPage],
  ] as const)('%s reads with keep_open, and leaving for another screen closes the walk', async (_n, path, read, page) => {
    vi.mocked(read).mockResolvedValue(page('walk-1') as never)
    const { router } = await mountApp(GRID_ROUTES, path)
    const query = (vi.mocked(read).mock.calls[0]![0] as { query: Record<string, unknown> }).query
    expect(query.keep_open).toBe(true)
    expect(closed()).toEqual([])

    await router.push('/overview')
    await flushPromises()
    expect(closed()).toEqual(['walk-1'])
  })

  it('opening a finding keeps the walk, so Back lands on the same page', async () => {
    vi.mocked(searchFindingsApiV1FindingsGet).mockResolvedValue(findingsPage('walk-1') as never)
    const { router } = await mountApp(GRID_ROUTES, '/findings')
    const grid = useFindingsStore()
    grid.goNext()
    await flushPromises()
    expect(grid.page).toBe(1)

    await router.push('/findings/CVE-2026-0001')
    await flushPromises()
    expect(closed()).toEqual([])
    expect(grid.page).toBe(1)
  })

  it('leaving for another screen brings the grid back on page 1', async () => {
    vi.mocked(searchFindingsApiV1FindingsGet).mockResolvedValue(findingsPage('walk-1') as never)
    const { router } = await mountApp(GRID_ROUTES, '/findings')
    const grid = useFindingsStore()
    grid.goNext()
    await flushPromises()
    await router.push('/overview')
    await flushPromises()
    expect(grid.page).toBe(0)
    expect(grid.activeCursor).toBeNull()
  })

  it('a first page that a newer read replaced has its walk closed; the shown one is kept', async () => {
    let answerOld: (v: unknown) => void = () => {}
    vi.mocked(searchFindingsApiV1FindingsGet)
      .mockImplementationOnce(() => new Promise((resolve) => (answerOld = resolve)) as never)
      .mockResolvedValue(findingsPage('walk-new') as never)
    await mountApp(GRID_ROUTES, '/findings')
    useFindingsStore().setSort('epss') // a new first page while the old one is still out
    await flushPromises()
    answerOld(findingsPage('walk-old'))
    await flushPromises()
    expect(closed()).toEqual(['walk-old'])
  })

  it('a past-T findings walk holds no search, so nothing is closed', async () => {
    useTimeTravelStore().rewindTo('2026-09-01T00:00:00Z')
    vi.mocked(searchFindingsApiV1FindingsGet).mockResolvedValue(findingsPage('past-1') as never)
    const { router } = await mountApp(GRID_ROUTES, '/findings')
    await router.push('/overview')
    await flushPromises()
    expect(closed()).toEqual([])
  })
})

describe('the image findings panel', () => {
  it('reads with keep_open, and leaving the image closes its walk', async () => {
    vi.mocked(searchFindingsApiV1FindingsGet).mockResolvedValue(findingsPage('img-1') as never)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/findings/:cveId', name: 'finding', component: { template: '<div />' } },
      ],
    })
    await router.push('/')
    const w = mount(ImageFindingsPanel, {
      props: { digest: 'sha256:abc', scanner: 'trivy' },
      global: { plugins: [router, [PrimeVue, { unstyled: true }]] },
    })
    await flushPromises()
    const query = (vi.mocked(searchFindingsApiV1FindingsGet).mock.calls[0]![0] as { query: Record<string, unknown> }).query
    expect(query.keep_open).toBe(true)
    expect(closed()).toEqual([])
    w.unmount()
    expect(closed()).toEqual(['img-1'])
  })
})

describe('one-shot reads close their walk at once', () => {
  const DETAIL = '/findings/CVE-2026-0001?digest=sha256:abc&scanner=trivy&pkg=pkg&ver=1.0'
  const DETAIL_ROUTES = [{ path: '/findings/:cveId', name: 'finding', component: FindingDetailView }]

  it('Finding detail: the pair, the occurrences and the activity', async () => {
    vi.mocked(searchFindingsApiV1FindingsGet).mockImplementation(
      async (opts) =>
        findingsPage((opts as { query: { size: number } }).query.size === 10 ? 'pair' : 'occ') as never,
    )
    vi.mocked(readAuditLogApiV1AuditGet).mockResolvedValue(auditPage('activity') as never)
    await mountApp(DETAIL_ROUTES, DETAIL)
    expect(closed().sort()).toEqual(['activity', 'occ', 'pair'])
  })

  it('Finding detail at a past T: only the activity, the one read that holds a search', async () => {
    useTimeTravelStore().rewindTo('2026-09-01T00:00:00Z')
    vi.mocked(searchFindingsApiV1FindingsGet).mockResolvedValue(findingsPage('past') as never)
    vi.mocked(readAuditLogApiV1AuditGet).mockResolvedValue(auditPage('activity') as never)
    await mountApp(DETAIL_ROUTES, DETAIL)
    expect(closed()).toEqual(['activity'])
  })

  it('the Contributors activity feed', async () => {
    vi.mocked(readAuditLogApiV1AuditGet).mockResolvedValue(auditPage('feed') as never)
    mount(ActivityFeed, {
      props: { query: { cluster_id: CLUSTER } },
      global: { plugins: [createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })] },
    })
    await flushPromises()
    expect(closed()).toEqual(['feed'])
  })
})

describe('closing a cursor', () => {
  it('sends the cursor, and closes every walk still held when the page goes, with keepalive', async () => {
    holdCursor('kept-a')
    holdCursor('kept-b')
    releaseCursor('kept-b') // a walk that ended: nothing left to close
    closeCursor('now')
    window.dispatchEvent(new Event('pagehide'))
    await flushPromises()
    const calls = vi.mocked(closeCursorApiV1CursorsClosePost).mock.calls.map((c) => c[0] as { body: { cursor: string }; keepalive: boolean })
    // the held set is module-wide, so walks of grids other tests left mounted close here too
    expect(calls).toContainEqual(expect.objectContaining({ body: { cursor: 'now' }, keepalive: false }))
    expect(calls).toContainEqual(expect.objectContaining({ body: { cursor: 'kept-a' }, keepalive: true }))
    expect(calls.map((c) => c.body.cursor)).not.toContain('kept-b')
  })

  it('closeUnpaged closes only a live cursor', () => {
    closeUnpaged(null, true)
    closeUnpaged(undefined, true)
    closeUnpaged('past', false)
    closeUnpaged('live', true)
    expect(closed()).toEqual(['live'])
  })
})

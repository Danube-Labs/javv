/**
 * Every read that issue 749 found checking only `response.ok` before reading `data` (ruling 1 on
 * the issue). Here every SDK call answers OK with a body that could not be read (`okWithoutBody()`):
 * each component must show its own failure copy, with no error for Vue and no rejection nothing
 * caught. Whatever else a component reads on mount gets the same reply, so an unguarded read in a
 * child fails here too.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref, type Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) => {
  const { okWithoutBody } = await import('./helpers/okWithoutBody')
  const real = await importOriginal<Record<string, unknown>>()
  return Object.fromEntries(
    Object.entries(real).map(([name, value]) => [
      name,
      typeof value === 'function' ? vi.fn<() => Promise<never>>(async () => okWithoutBody()) : value,
    ]),
  )
})
vi.mock('@/api/client', () => ({ client: {} }))

import { mintApiV1AdminTokensPost, rotateApiV1AdminTokensTokenIdRotatePost } from '@/api/generated'
import AuditLens from '@/components/dashboards/AuditLens.vue'
import ActivityFeed from '@/components/contributors/ActivityFeed.vue'
import ProgressPanel from '@/components/contributors/ProgressPanel.vue'
import TopComponentsCard from '@/components/overview/TopComponentsCard.vue'
import IngestFailuresTable from '@/components/scanners/IngestFailuresTable.vue'
import { useGlobalSearch } from '@/composables/useGlobalSearch'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'
import ApprovalsView from '@/views/ApprovalsView.vue'
import ContributorsView from '@/views/ContributorsView.vue'
import DashboardsView from '@/views/DashboardsView.vue'
import SavedViewsView from '@/views/SavedViewsView.vue'
import ScannerStatusView from '@/views/ScannerStatusView.vue'
import ScanningView from '@/views/settings/ScanningView.vue'
import DataOpenSearchView from '@/views/settings/DataOpenSearchView.vue'
import ScanScopeView from '@/views/settings/ScanScopeView.vue'
import SlaPolicyView from '@/views/settings/SlaPolicyView.vue'
import TokensView from '@/views/settings/TokensView.vue'
import UsersRolesView from '@/views/settings/UsersRolesView.vue'
import { useFleetClusters } from '@/views/settings/clusterRetirement'
import { useRetirementWindow } from '@/views/settings/retirementForm'

const CLUSTER = 'c-k3d-0001'
const query = { cluster_id: CLUSTER }

let thrown: string[] = []
const onRejection = (reason: unknown) => void thrown.push(`unhandled: ${String(reason)}`)

function mountAll(component: Component, props: Record<string, unknown> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
  })
  return mount(component, {
    props,
    global: {
      plugins: [router],
      stubs: { EChart: true },
      config: { errorHandler: (err) => void thrown.push((err as Error).message) },
    },
  })
}

beforeEach(() => {
  // back to the factory's no-body reply: an override in one test must not reach the next
  vi.resetAllMocks()
  setActivePinia(createPinia())
  useClusterStore().selectedId = CLUSTER
  thrown = []
  process.on('unhandledRejection', onRejection)
})
afterEach(() => {
  process.off('unhandledRejection', onRejection)
})

describe('a component whose OK reply has a body that could not be read shows its failure copy', () => {
  it.each([
    ['ActivityFeed', ActivityFeed, { query }, 'Recent activity unavailable.'],
    ['ProgressPanel', ProgressPanel, { query }, 'Triage progress unavailable.'],
    ['AuditLens', AuditLens, { query }, 'Audit activity unavailable.'],
    ['ContributorsView', ContributorsView, {}, 'Contributors unavailable.'],
    ['IngestFailuresTable', IngestFailuresTable, { clusterId: CLUSTER, scanner: 'trivy', t: null }, 'Failed ingests unavailable.'],
    ['ScannerStatusView', ScannerStatusView, {}, 'Scanner status unavailable.'],
    ['SavedViewsView', SavedViewsView, {}, 'Saved views unavailable.'],
    ['DashboardsView', DashboardsView, {}, 'Dashboards unavailable.'],
    ['ScanScopeView', ScanScopeView, {}, 'Scan scope unavailable.'],
    ['ScanningView', ScanningView, {}, 'Staleness timers unavailable.'],
    ['SlaPolicyView', SlaPolicyView, {}, 'SLA policy unavailable.'],
    ['TokensView', TokensView, {}, 'Token list unavailable.'],
    ['UsersRolesView', UsersRolesView, {}, 'User list unavailable.'],
    // these three did not throw: they showed a loaded page with nothing, or with old data, in it
    ['TopComponentsCard', TopComponentsCard, { scanner: 'all' }, 'Component ranking unavailable.'],
    ['DataOpenSearchView', DataOpenSearchView, {}, 'Data settings unavailable.'],
    ['ApprovalsView', ApprovalsView, {}, 'Could not load the queue.'],
  ] as const)('%s', async (_name, component, props, copy) => {
    const w = mountAll(component as Component, props)
    await flushPromises()
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.text()).toContain(copy)
  })
})

// a guard over two replies needs each half: here only one of them has a body that could not be read
describe('a component with two reads, only one of which has a body that could not be read', () => {
  const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
  const sdk = () => import('@/api/generated')

  it.each(['first', 'second'] as const)('ProgressPanel, the %s facets read', async (which) => {
    const { facetFindingsApiV1FindingsFacetsGet: facets } = await sdk()
    const { okWithoutBody } = await import('./helpers/okWithoutBody')
    const whole = ok({ facets: { severity: [] } })
    vi.mocked(facets)
      .mockResolvedValueOnce(which === 'first' ? okWithoutBody() : whole)
      .mockResolvedValueOnce(which === 'second' ? okWithoutBody() : whole)
    const w = mountAll(ProgressPanel, { query })
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.text()).toContain('Triage progress unavailable.')
  })

  it.each(['freshness', 'provenance'] as const)('ScannerStatusView, with %s whole', async (whole) => {
    const s = await sdk()
    const call = whole === 'freshness' ? s.scannerFreshnessApiV1ScannersFreshnessGet : s.scannerProvenanceApiV1ScannersProvenanceGet
    vi.mocked(call).mockResolvedValue(ok({ scanners: [] }))
    const w = mountAll(ScannerStatusView)
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.text()).toContain('Scanner status unavailable.')
  })

  it.each(['users', 'roles'] as const)('UsersRolesView, with %s whole', async (whole) => {
    const s = await sdk()
    if (whole === 'users') vi.mocked(s.listUsersApiV1AdminUsersGet).mockResolvedValue(ok({ users: [] }))
    else vi.mocked(s.listRolesApiV1AdminRolesGet).mockResolvedValue(ok({ roles: [] }))
    const w = mountAll(UsersRolesView)
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.text()).toContain('User list unavailable.')
  })

  it('ScanningView, with the timers whole: the page loads its timers', async () => {
    const s = await sdk()
    vi.mocked(s.getStalenessApiV1SettingsStalenessGet).mockResolvedValue(
      ok({ staleness: { freshness_days: 7, scanner_down_days: 3 }, per_cluster_override: false }),
    )
    const w = mountAll(ScanningView)
    await flushPromises()
    expect(thrown).toEqual([])
    expect(w.text()).not.toContain('Staleness timers unavailable.')
    // loaded, not merely not failed: the form holds the timers the read returned
    expect((w.find('input').element as HTMLInputElement).value).toBe('7')
  })
})

describe('a composable whose OK reply has a body that could not be read reports a failure', () => {
  it('useFleetClusters', async () => {
    const fleet = useFleetClusters()
    await fleet.load()
    expect(fleet.failed.value).toBe(true)
    expect(fleet.rows.value).toEqual([])
  })

  it('useRetirementWindow', async () => {
    const scope = effectScope()
    const form = scope.run(() => useRetirementWindow(ref(CLUSTER), ref(7)))!
    await flushPromises()
    expect(thrown).toEqual([])
    expect(form.failed.value).toBe(true)
    scope.stop()
  })

  it('useGlobalSearch', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    const search = useGlobalSearch(() => CLUSTER)
    search.search('openssl')
    vi.advanceTimersByTime(300)
    vi.useRealTimers()
    await flushPromises()
    expect(thrown).toEqual([])
    expect(search.failed.value).toBe(true)
  })
})

// ruling 3 on the issue: the token exists, but its value never reached the page
describe('a mint or rotate whose OK reply has a body that could not be read', () => {
  const LOST = 'The token was created, but its value did not reach this page. Rotate it to get a value you can copy.'
  const ROW = { id: 't-1', cluster_id: CLUSTER, scanner: 'trivy', enabled: true, created_at: null, expires_at: null, last_used_at: null }

  async function tokensWithOneRow() {
    const sdk = await import('@/api/generated')
    vi.mocked(sdk.listTokensApiV1AdminTokensGet).mockResolvedValue({
      data: { tokens: [ROW], total: 1 },
      response: { ok: true, status: 200 },
    } as never)
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue({
      data: { clusters: [{ cluster_id: CLUSTER, cluster_name: 'alpha' }] },
      response: { ok: true, status: 200 },
    } as never)
    const w = mountAll(TokensView)
    await flushPromises()
    return w
  }

  it('a mint says the value was lost and points to Rotate', async () => {
    const w = await tokensWithOneRow()
    await w.findAll('button').find((b) => b.text().includes('Mint token'))!.trigger('click')
    await flushPromises()
    // the dialog's submit carries the same label as the button that opened it
    const submit = w.findAll('button').filter((b) => b.text().includes('Mint token')).at(-1)!
    await submit.trigger('click')
    await flushPromises()
    expect(vi.mocked(mintApiV1AdminTokensPost)).toHaveBeenCalled()
    expect(thrown).toEqual([])
    expect(useToastStore().toasts.map((t) => t.message)).toContain(LOST)
  })

  it('a rotate says the same', async () => {
    const w = await tokensWithOneRow()
    await w.findAll('button').find((b) => b.text() === 'Rotate')!.trigger('click')
    await flushPromises()
    await w.findAll('button').filter((b) => b.text() === 'Rotate').at(-1)!.trigger('click')
    await flushPromises()
    expect(vi.mocked(rotateApiV1AdminTokensTokenIdRotatePost)).toHaveBeenCalled()
    expect(thrown).toEqual([])
    expect(useToastStore().toasts.map((t) => t.message)).toContain(LOST)
  })
})

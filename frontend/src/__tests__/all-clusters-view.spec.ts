import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'

import LimitedHistoricalNotice from '@/components/dashboards/LimitedHistoricalNotice.vue'
import { useGlobalUrlStamp } from '@/composables/useGlobalUrlStamp'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import AllClustersView from '@/views/AllClustersView.vue'

const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } })

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
    facetFindingsApiV1FindingsFacetsGet: vi.fn<() => Promise<unknown>>(),
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
    listRunningImagesApiV1ImagesGet: vi.fn<() => Promise<unknown>>(),
    // the health chips threshold on the live fleet timers (M9e banner rework)
    getStalenessApiV1SettingsStalenessGet: vi.fn<() => Promise<unknown>>().mockResolvedValue({
      data: { staleness: { freshness_days: 3, scanner_down_days: 7 }, per_cluster_override: false },
      response: { ok: true, status: 200 },
    }),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import {
  facetFindingsApiV1FindingsFacetsGet,
  listClustersApiV1ClustersGet,
  listRunningImagesApiV1ImagesGet,
  scannerFreshnessApiV1ScannersFreshnessGet,
} from '@/api/generated'

const listMock = vi.mocked(listClustersApiV1ClustersGet)
const facetsMock = vi.mocked(facetFindingsApiV1FindingsFacetsGet)
const freshMock = vi.mocked(scannerFreshnessApiV1ScannersFreshnessGet)
const imagesMock = vi.mocked(listRunningImagesApiV1ImagesGet)

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/overview', component: { template: '<div />' } },
  ],
})

const mountView = () => mount(AllClustersView, { global: { plugins: [router] } })

describe('AllClustersView (M9c slice 2)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('T<now replaces the screen with LimitedHistoricalNotice — no table, no query (I3)', async () => {
    useTimeTravelStore().t = '2026-07-01T00:00:00Z'
    const w = mountView()
    await flushPromises()
    expect(w.findComponent(LimitedHistoricalNotice).exists()).toBe(true)
    expect(w.find('table').exists()).toBe(false)
    expect(listMock).not.toHaveBeenCalled()
    expect(facetsMock).not.toHaveBeenCalled()
  })

  it('T=now renders a row per cluster with one mix bar PER SCANNER, never merged', async () => {
    listMock.mockResolvedValue(ok({ clusters: [{ cluster_id: 'c-1', cluster_name: 'prod' }] }) as never)
    facetsMock.mockResolvedValue(
      ok({
        facets: {
          severity: [
            { key: 'critical', count: 3, by_scanner: { trivy: 1, grype: 2 } },
            { key: 'low', count: 5, by_scanner: { trivy: 5 } },
          ],
          present: [{ key: 'true', count: 8, by_scanner: { trivy: 6, grype: 2 } }],
        },
      }) as never,
    )
    freshMock.mockResolvedValue(
      ok({ scanners: [{ scanner: 'trivy', last_ingest_at: '2026-07-10T12:00:00Z', silent_for_seconds: 60 }] }) as never,
    )
    imagesMock.mockResolvedValue(ok({ inventory: { inventory_run_id: 'r1' }, images: [{ replicas: 4 }] }) as never)

    const w = mountView()
    await flushPromises()

    expect(w.findComponent(LimitedHistoricalNotice).exists()).toBe(false)
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.text()).toContain('prod')
    expect(rows[0]!.findAll('.mix-row')).toHaveLength(2) // trivy + grype, side by side
    expect(rows[0]!.text()).toContain('8') // present count verbatim
    // fleet strip: the critical cell shows the server bucket count
    expect(w.find('.fleet-band').text()).toContain('critical')
    // signal columns (operator A/B ruling: explicit columns) — headers + per-row values
    const headers = w.findAll('th').map((h) => h.text())
    for (const h of ['KEV', 'Fix %', 'Disagree', 'Triage']) expect(headers).toContain(h)
    expect(rows[0]!.find('.kev-alarm').exists()).toBe(false) // kev bucket absent → 0, no alarm
    expect(rows[0]!.text()).toContain('%') // fix % renders
  })

  it('the header card shows no cluster count while the fleet loads, then the count (issue 902)', async () => {
    listMock.mockResolvedValue(ok({ clusters: [{ cluster_id: 'c-1', cluster_name: 'prod' }] }) as never)
    let answer!: (v: unknown) => void
    facetsMock.mockReturnValue(new Promise((res) => (answer = res)) as never)
    freshMock.mockResolvedValue(ok({ scanners: [] }) as never)
    imagesMock.mockResolvedValue(ok({ inventory: { inventory_run_id: 'r1' }, images: [] }) as never)
    const w = mountView()
    await flushPromises()
    const note = () => w.get('.head-note').text().replace(/\s+/g, ' ')
    expect(note()).toBe('Fleet current state')
    answer(ok({ facets: {} }))
    await flushPromises()
    expect(note()).toMatch(/^Fleet current state · 1 cluster · /)
  })

  it('no clusters → the cold-start copy, not an empty table', async () => {
    listMock.mockResolvedValue(ok({ clusters: [] }) as never)
    const w = mountView()
    await flushPromises()
    expect(w.find('.first-run').exists()).toBe(true)
    expect(w.find('table').exists()).toBe(false)
  })

  /** two clusters with c-1 selected, mounted beside the shell's URL stamp, like the app */
  async function mountFleetInShell() {
    listMock.mockResolvedValue(
      ok({
        clusters: [
          { cluster_id: 'c-1', cluster_name: 'prod' },
          { cluster_id: 'c-2', cluster_name: 'beta' },
        ],
      }) as never,
    )
    facetsMock.mockResolvedValue(ok({ facets: {} }) as never)
    freshMock.mockResolvedValue(ok({ scanners: [] }) as never)
    imagesMock.mockResolvedValue(ok({ inventory: { inventory_run_id: 'r1' }, images: [] }) as never)
    useClusterStore().selectedId = 'c-1'

    const shellRouter = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/clusters', component: AllClustersView },
        // lazy + an async guard, like the app: the navigation spans several ticks
        { path: '/overview', component: () => Promise.resolve({ render: () => h('div') }) },
      ],
    })
    shellRouter.beforeEach(async () => {
      await Promise.resolve()
      return true
    })
    await shellRouter.push('/clusters?cluster=c-1')
    const Shell = defineComponent({
      setup() {
        useGlobalUrlStamp()
        return () => h(RouterView)
      },
    })
    const w = mount(Shell, { global: { plugins: [shellRouter] } })
    await flushPromises()

    return { w, shellRouter }
  }

  // issue 666: the row click selects the cluster and opens Overview in one handler; with the
  // shell's URL stamp mounted beside the view, the stamp must not cancel that navigation
  it('one click on a cluster that is not selected opens its Overview, with that cluster', async () => {
    const { w, shellRouter } = await mountFleetInShell()

    const beta = w.findAll('tbody tr').find((r) => r.text().includes('beta'))
    expect(beta).toBeDefined()
    await beta!.trigger('click')
    await flushPromises()

    expect(shellRouter.currentRoute.value.path).toBe('/overview')
    expect(shellRouter.currentRoute.value.query.cluster).toBe('c-2')
  })
  // issue 674: the name is a real link, so the keyboard reaches the row. Enter on it is a
  // click on the link, and it must open exactly as the row does: select first, then navigate
  it('the cluster name is a link: activating it opens that cluster, and it carries a new-tab address', async () => {
    const { w, shellRouter } = await mountFleetInShell()

    const link = w.findAll('tbody tr a').find((a) => a.text().includes('beta'))
    expect(link).toBeDefined()
    expect(link!.attributes('href')).toBe('/overview?cluster=c-2')
    await link!.trigger('click')
    await flushPromises()

    expect(useClusterStore().selectedId).toBe('c-2')
    expect(shellRouter.currentRoute.value.path).toBe('/overview')
    expect(shellRouter.currentRoute.value.query.cluster).toBe('c-2')
  })
})

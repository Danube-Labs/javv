/**
 * The retirement countdown (issue 765): the pure status off one cluster listing row, the banner
 * line for the selected cluster, and the chip on All clusters, which moves on the banner's tick
 * from the list the banner re-reads (issue 787). Dates come from the backend's schedule; nothing
 * here re-derives a window.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import * as sdk from '@/api/generated'
import RetirementWindowCard from '@/components/settings/RetirementWindowCard.vue'
import RetirementCountdownBanner from '@/components/system/RetirementCountdownBanner.vue'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'
import {
  isUrgent,
  retirementChip,
  retirementCountdown,
  retirementStatus,
  silenceClause,
} from '@/system/retirement'
import AllClustersView from '@/views/AllClustersView.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
    facetFindingsApiV1FindingsFacetsGet: vi.fn<() => Promise<unknown>>(),
    scannerFreshnessApiV1ScannersFreshnessGet: vi.fn<() => Promise<unknown>>(),
    listRunningImagesApiV1ImagesGet: vi.fn<() => Promise<unknown>>(),
    getStalenessApiV1SettingsStalenessGet: vi.fn<() => Promise<unknown>>(),
    getRetirementApiV1SettingsRetirementGet: vi.fn<() => Promise<unknown>>(),
    putRetirementApiV1SettingsRetirementPut: vi.fn<() => Promise<unknown>>(),
  }),
)

afterEach(() => {
  vi.useRealTimers()
})

const DAY = 86_400_000
const NOW = Date.parse('2026-10-07T12:00:00Z')
const at = (days: number) => new Date(NOW + days * DAY).toISOString()

/** A row inside its warning window: silent 40 days, warned 2 days ago, retires in `left` days. */
const row = (left: number, over: Record<string, unknown> = {}) => ({
  cluster_id: 'c-beta',
  cluster_name: 'beta',
  retired: false,
  last_scan_at: at(-40),
  silent_since: at(-40),
  warns_at: at(-2),
  retires_at: at(left),
  ...over,
})

describe('retirementStatus', () => {
  it('is active without a schedule, with a never window, and before the warning starts', () => {
    expect(retirementStatus({}, NOW).kind).toBe('active')
    expect(retirementStatus(row(5, { warns_at: null, retires_at: null }), NOW).kind).toBe('active')
    expect(retirementStatus(row(5, { warns_at: at(1) }), NOW).kind).toBe('active')
  })

  it('is retired when the listing says so, whatever the dates', () => {
    expect(retirementStatus(row(5, { retired: true }), NOW).kind).toBe('retired')
  })

  it('counts whole days left rounding up, never below one', () => {
    expect(retirementStatus(row(4.6), NOW)).toEqual({ kind: 'warning', days: 5, silentDays: 40 })
    expect(retirementStatus(row(0.1), NOW)).toEqual({ kind: 'warning', days: 1, silentDays: 40 })
  })

  it('reads the silence from the last scan, not from where the countdown starts', () => {
    // a cluster brought back from retirement: its countdown starts at the return, its last scan
    // is older, and "no scans for" must name the scan
    const back = row(5, { last_scan_at: at(-60), silent_since: at(-40) })
    expect(retirementStatus(back, NOW)).toMatchObject({ silentDays: 60 })
    expect(retirementStatus(row(5, { last_scan_at: null }), NOW)).toMatchObject({ silentDays: null })
  })

  it('is held once past its date and still listed', () => {
    expect(retirementStatus(row(-0.5), NOW)).toEqual({ kind: 'held', silentDays: 40 })
  })
})

describe('the countdown copy', () => {
  it('says how long it has been silent and how long is left', () => {
    const s = retirementStatus(row(5), NOW)
    expect(silenceClause(s)).toBe('has sent no scans for 40 days.')
    expect(retirementCountdown(s)).toBe('It will be retired in 5 days unless a scan arrives.')
    expect(silenceClause(retirementStatus(row(1, { last_scan_at: null }), NOW))).toBe('has never sent a scan.')
    expect(retirementCountdown(retirementStatus(row(1), NOW))).toBe('It will be retired in 1 day unless a scan arrives.')
  })

  it('says nothing outside the window', () => {
    const s = retirementStatus(row(5, { warns_at: at(1) }), NOW)
    expect(silenceClause(s)).toBeNull()
    expect(retirementCountdown(s)).toBeNull()
    expect(retirementChip(s)).toBeNull()
  })

  it('turns red on the last day and once past its date', () => {
    expect(isUrgent(retirementStatus(row(2), NOW))).toBe(false)
    expect(isUrgent(retirementStatus(row(1), NOW))).toBe(true)
    expect(isUrgent(retirementStatus(row(-1), NOW))).toBe(true)
    expect(retirementChip(retirementStatus(row(5), NOW))).toEqual({ label: 'retires in 5 days', tone: 'warn' })
    expect(retirementChip(retirementStatus(row(-1), NOW))).toEqual({ label: 'retirement due', tone: 'down' })
  })
})

describe('the only cluster listed', () => {
  it('gets no countdown, no red and no chip: the sweep never retires it', () => {
    for (const left of [5, 1, -1]) {
      const s = retirementStatus(row(left), NOW)
      expect(retirementCountdown(s, true)).toMatch(/As the only cluster, it is not retired automatically/)
      expect(isUrgent(s, true)).toBe(false)
      expect(retirementChip(s, true)).toBeNull()
    }
  })
})

describe('useClusterStore.refresh', () => {
  const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('keeps a selection that is still listed, even one that was never remembered', async () => {
    localStorage.setItem('javv.selected_cluster_id', 'c-alpha')
    const store = useClusterStore()
    store.selectedId = 'c-beta' // a deep link: selected, not remembered
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue(
      ok({ clusters: [row(5), row(5, { cluster_id: 'c-alpha', cluster_name: 'alpha' })] }),
    )
    await store.refresh()
    expect(store.selectedId).toBe('c-beta')
    expect(store.selected?.retires_at).toBe(at(5))
  })

  it('falls back when the selected cluster left the list (retired meanwhile)', async () => {
    localStorage.setItem('javv.selected_cluster_id', 'c-alpha')
    const store = useClusterStore()
    store.clusters = [row(5)]
    store.selectedId = 'c-beta'
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue(
      ok({ clusters: [row(5, { cluster_id: 'c-alpha', cluster_name: 'alpha' })] }),
    )
    await store.refresh()
    expect(store.selectedId).toBe('c-alpha')
    // every screen re-scopes to another tenant: say so
    expect(JSON.stringify(useToastStore().$state)).toContain(
      'beta is no longer on the cluster list. Showing alpha.',
    )
  })

  it('keeps the newest answer: an older poll landing late does not undo a later re-read', async () => {
    const store = useClusterStore()
    store.selectedId = 'c-alpha'
    const alpha = row(5, { cluster_id: 'c-alpha', cluster_name: 'alpha' })
    let answerPoll: (v: unknown) => void = () => {}
    vi.mocked(sdk.listClustersApiV1ClustersGet)
      .mockReturnValueOnce(new Promise((r) => (answerPoll = r)) as never) // the tick, in flight
      .mockResolvedValueOnce(ok({ clusters: [alpha] })) // the re-read after retiring beta
    const poll = store.refresh()
    await store.refresh()
    answerPoll(ok({ clusters: [alpha, row(5)] }))
    await poll
    expect(store.clusters.map((c) => c.cluster_id)).toEqual(['c-alpha'])
  })

  it('clears a failed first load once a re-read succeeds', async () => {
    const store = useClusterStore()
    store.failed = true
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue(ok({ clusters: [row(5)] }))
    await store.refresh()
    expect(store.failed).toBe(false)
  })
})

describe('RetirementCountdownBanner', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
  })

  /** Selects `entry` in a fleet of two: alpha is scanning, outside its window. */
  function select(entry: ReturnType<typeof row>) {
    const store = useClusterStore()
    store.clusters = [entry, row(5, { cluster_id: 'c-alpha', cluster_name: 'alpha', warns_at: at(30) })]
    store.selectedId = entry.cluster_id
  }

  it('names the cluster, its silence and the days left, amber while there is time', () => {
    select(row(5))
    const w = mount(RetirementCountdownBanner)
    const line = w.find('.retire-line')
    expect(line.text()).toBe('beta has sent no scans for 40 days. It will be retired in 5 days unless a scan arrives.')
    expect(line.classes()).toContain('tone-degraded')
    expect(line.attributes('role')).toBe('status')
    w.unmount()
  })

  it('is an alert on the last day', () => {
    select(row(1))
    const w = mount(RetirementCountdownBanner)
    const line = w.find('.retire-line')
    expect(line.classes()).toContain('tone-down')
    expect(line.attributes('role')).toBe('alert')
    w.unmount()
  })

  it('shows nothing before the warning starts', () => {
    select(row(5, { warns_at: at(1) }))
    const w = mount(RetirementCountdownBanner)
    expect(w.find('.retire-line').exists()).toBe(false)
    w.unmount()
  })

  it('past its date it is an alert that the sweep retires it unless a scan arrives', () => {
    select(row(-0.5))
    const w = mount(RetirementCountdownBanner)
    const line = w.find('.retire-line')
    expect(line.attributes('role')).toBe('alert')
    expect(line.text()).toContain('the next retirement sweep retires it unless a scan arrives')
    w.unmount()
  })

  it('is amber and says why for the only cluster, with no countdown', () => {
    select(row(1))
    useClusterStore().clusters = [row(1)]
    const w = mount(RetirementCountdownBanner)
    const line = w.find('.retire-line')
    expect(line.classes()).toContain('tone-degraded')
    expect(line.text()).toContain('As the only cluster, it is not retired automatically')
    w.unmount()
  })

  it('re-reads the list on its tick: a scan that arrived clears it', async () => {
    vi.useFakeTimers({ now: NOW, toFake: ['Date', 'setInterval', 'clearInterval'] })
    const store = useClusterStore()
    store.clusters = [row(5), row(5, { cluster_id: 'c-alpha', cluster_name: 'alpha', warns_at: at(9) })]
    store.selectedId = 'c-beta'
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue({
      response: { ok: true, status: 200 },
      // beta scanned: its schedule moved out of the warning window; alpha is still listed, so
      // this is not the only-cluster case
      data: {
        clusters: [
          row(5, { last_scan_at: at(0), warns_at: at(38), retires_at: at(45) }),
          row(5, { cluster_id: 'c-alpha', cluster_name: 'alpha', warns_at: at(9) }),
        ],
      },
    } as never)
    const w = mount(RetirementCountdownBanner)
    expect(w.find('.retire-line').exists()).toBe(true)
    vi.advanceTimersByTime(10 * 60_000)
    await flushPromises()
    expect(w.find('.retire-line').exists()).toBe(false)
    w.unmount()
  })
})

describe('saving the retirement window', () => {
  it('re-reads the cluster list, so the banner shows the new schedule', async () => {
    setActivePinia(createPinia())
    const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
    vi.mocked(sdk.getRetirementApiV1SettingsRetirementGet).mockResolvedValue(
      ok({ retirement: { retire_after_days: 45, warn_days: 7 }, per_cluster_override: false }),
    )
    vi.mocked(sdk.getStalenessApiV1SettingsStalenessGet).mockResolvedValue(
      ok({ staleness: { freshness_days: 3, scanner_down_days: 7 }, per_cluster_override: false }),
    )
    vi.mocked(sdk.putRetirementApiV1SettingsRetirementPut).mockResolvedValue(ok({}))
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue(ok({ clusters: [row(5)] }))
    useClusterStore().clusters = [row(5)]
    useClusterStore().selectedId = 'c-beta'
    const w = mount(RetirementWindowCard)
    await flushPromises()
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockClear()
    await w.find('input#retire-after').setValue('90')
    await w.findAll('button').find((b) => b.text().startsWith('Save'))!.trigger('click')
    await flushPromises()
    expect(sdk.listClustersApiV1ClustersGet).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})

describe('All clusters countdown chip', () => {
  const ok = (data: unknown) => ({ data, response: { ok: true, status: 200 } }) as never
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/overview', component: { template: '<div />' } },
    ],
  })

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.useFakeTimers({ now: NOW, toFake: ['Date'] })
    vi.mocked(sdk.facetFindingsApiV1FindingsFacetsGet).mockResolvedValue(ok({ facets: {} }))
    vi.mocked(sdk.scannerFreshnessApiV1ScannersFreshnessGet).mockResolvedValue(ok({ scanners: [] }))
    vi.mocked(sdk.listRunningImagesApiV1ImagesGet).mockResolvedValue(ok({ inventory: null, images: [] }))
    vi.mocked(sdk.getStalenessApiV1SettingsStalenessGet).mockResolvedValue(
      ok({ staleness: { freshness_days: 3, scanner_down_days: 7 }, per_cluster_override: false }),
    )
  })

  it('shows under the name of a cluster inside its window only', async () => {
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue(
      ok({ clusters: [row(5), row(5, { cluster_id: 'c-alpha', cluster_name: 'alpha', warns_at: at(3) })] }),
    )
    const w = mount(AllClustersView, { global: { plugins: [router] } })
    await flushPromises()
    const [beta, alpha] = w.findAll('tbody tr')
    expect(beta!.find('.cluster-info').text()).toContain('retires in 5 days')
    expect(alpha!.text()).not.toContain('retires in')
  })

  const alpha = row(5, { cluster_id: 'c-alpha', cluster_name: 'alpha', warns_at: at(30) })
  const chip = (w: ReturnType<typeof mount>) => w.findAll('tbody tr')[0]!.find('.cluster-info').text()

  it("moves on the banner's 10-minute tick while the page stays open (issue 787)", async () => {
    vi.useFakeTimers({ now: NOW, toFake: ['Date', 'setInterval', 'clearInterval'] })
    // 1 day and 5 minutes left: 2 days rounded up, then 1 day once the tick has passed
    const beta = row(1, { retires_at: new Date(NOW + DAY + 5 * 60_000).toISOString() })
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue(ok({ clusters: [beta, alpha] }))
    const w = mount(AllClustersView, { global: { plugins: [router] } })
    await flushPromises()
    expect(chip(w)).toContain('retires in 2 days')
    vi.advanceTimersByTime(10 * 60_000)
    await flushPromises()
    expect(chip(w)).toContain('retires in 1 day')
    expect(sdk.facetFindingsApiV1FindingsFacetsGet).toHaveBeenCalledTimes(2) // no reload
    w.unmount()
  })

  it('reads the cluster list the banner re-reads: a cluster that scanned loses its chip', async () => {
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue(ok({ clusters: [row(5), alpha] }))
    const w = mount(AllClustersView, { global: { plugins: [router] } })
    await flushPromises()
    expect(chip(w)).toContain('retires in 5 days')
    // the banner's re-read: beta scanned, its schedule left the warning window
    useClusterStore().clusters = [row(5, { last_scan_at: at(0), warns_at: at(38), retires_at: at(45) }), alpha]
    await flushPromises()
    expect(chip(w)).not.toContain('retires in')
    w.unmount()
  })
})

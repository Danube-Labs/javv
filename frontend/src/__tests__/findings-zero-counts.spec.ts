/**
 * Findings shows 0 for a flag with no rows, and no count for a flag the scan history does not
 * record at a past time (issue 980). At a past time the server sends KEV and Scanners disagree as
 * empty lists, because it cannot count them: those are no counts, not counts of 0. The time of
 * the read that answered decides, not the time the screen shows while the next read runs.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import PrimeVue from 'primevue/config'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

vi.mock('@/api/generated', async (importOriginal) => {
  const real = await importOriginal<Record<string, unknown>>()
  return Object.fromEntries(
    Object.entries(real).map(([name, value]) => [
      name,
      // every other read stays open: this spec looks only at the filter list
      typeof value === 'function' ? vi.fn<() => Promise<never>>(() => new Promise<never>(() => {})) : value,
    ]),
  )
})
vi.mock('@/api/client', () => ({ client: {} }))

import { facetFindingsApiV1FindingsFacetsGet } from '@/api/generated'
import type { FacetsResponse } from '@/filters/facets'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import FindingsView from '@/views/FindingsView.vue'

const CLUSTER = 'c-k3d-0001'
const PAST = '2026-10-01T00:00:00.000Z'

// what the server sends at a past time: KEV and Scanners disagree are empty lists there
const COUNTS: FacetsResponse = {
  kev: [],
  disagree: [],
  fixable: [{ key: 'true', count: 14, by_scanner: { trivy: 14 } }],
  overdue: [{ key: 'true', count: 21, by_scanner: { trivy: 21 } }],
  unassigned: [{ key: 'true', count: 0, by_scanner: {} }],
}
const answer = (facets: FacetsResponse) => ({ data: { facets }, request: {}, response: { ok: true, status: 200 } })

async function mountFindings() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
  })
  await router.push('/')
  const w = mount(FindingsView as Component, {
    global: { plugins: [router, [PrimeVue, { unstyled: true }]], stubs: { EChart: true } },
  })
  await flushPromises()
  return w
}

/** The count a rail row shows, or null when it shows none. */
function railCount(w: Awaited<ReturnType<typeof mountFindings>>, label: string): string | null {
  const row = w.findAll('.facets .facet-row').find((r) => r.find('.facet-text').text() === label)
  if (!row) throw new Error(`no rail row ${label}`)
  const count = row.find('.facet-count')
  return count.exists() ? count.text() : null
}

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.clusters = [{ cluster_id: CLUSTER, cluster_name: 'k3d' }] as never
  clusters.selectedId = CLUSTER
  clusters.loaded = true
  vi.mocked(facetFindingsApiV1FindingsFacetsGet).mockImplementation(async () => answer(COUNTS) as never)
})

describe('Findings: a flag with no rows, now and at a past time (issue 980)', () => {
  it('now, a flag the server counted with no rows shows 0', async () => {
    const w = await mountFindings()
    expect(railCount(w, 'KEV')).toBe('0')
    expect(railCount(w, 'Scanners disagree')).toBe('0')
    expect(railCount(w, 'Unassigned')).toBe('0')
    expect(railCount(w, 'Fix available')).toBe('14')
  })

  it('at a past time, KEV and Scanners disagree show no count; the counted flags keep theirs', async () => {
    useTimeTravelStore().t = PAST
    const w = await mountFindings()
    const [call] = vi.mocked(facetFindingsApiV1FindingsFacetsGet).mock.lastCall!
    expect((call as { query: Record<string, unknown> }).query.as_of).toBe(PAST)
    expect(railCount(w, 'KEV')).toBeNull()
    expect(railCount(w, 'Scanners disagree')).toBeNull()
    expect(railCount(w, 'Unassigned')).toBe('0')
    expect(railCount(w, 'Fix available')).toBe('14')
  })

  it('the time of the read that answered decides, while the next read runs', async () => {
    useTimeTravelStore().t = PAST
    const w = await mountFindings()
    vi.mocked(facetFindingsApiV1FindingsFacetsGet).mockImplementation(() => new Promise(() => {}) as never)
    useTimeTravelStore().t = null
    await flushPromises()
    // the rail still shows the past-time answer, and that answer did not count KEV
    expect(railCount(w, 'KEV')).toBeNull()
  })
})

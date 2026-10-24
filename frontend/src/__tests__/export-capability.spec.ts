/**
 * The export controls follow `can_export` (issue 243, ruling 3, option A on built pictures): a role
 * without it still sees the control, disabled, with a key and the reason next to it, and the control
 * points at that reason for a screen reader. The backend refuses the files with 403 either way
 * (backend tests/security/test_export_capability.py); this spec pins what each screen shows.
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

import { contributorsApiV1ContributorsGet, listRunningImagesApiV1ImagesGet } from '@/api/generated'
import ExportDialog from '@/components/findings/ExportDialog.vue'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { NO_EXPORT_NOTE, useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import ApprovalsView from '@/views/ApprovalsView.vue'
import AuditTrailView from '@/views/AuditTrailView.vue'
import ContributorsView from '@/views/ContributorsView.vue'
import ImagesView from '@/views/ImagesView.vue'

const CLUSTER = 'c-k3d-0001'

async function mountRouted(component: Component, props: Record<string, unknown> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      // the leaderboard links each user to their Audit log rows
      { path: '/audit', name: 'audit', component: { template: '<div />' } },
      { path: '/:any(.*)*', component: { template: '<div />' } },
    ],
  })
  await router.push('/')
  const w = mount(component, {
    props,
    global: { plugins: [router, [PrimeVue, { unstyled: true }]], stubs: { EChart: true } },
  })
  await flushPromises()
  return w
}

function signIn(capabilities: string[]) {
  useAuthStore().user = { username: 'vera', role: 'custom', capabilities, must_change: false } as never
}

const SCREENS = [
  ['Findings', ExportDialog, { fields: FINDINGS_FIELDS, selections: {}, modes: {}, historical: false }],
  ['Audit log', AuditTrailView, {}],
  ['Contributors', ContributorsView, {}],
  ['Approval list', ApprovalsView, {}],
  ['Running images', ImagesView, {}],
] as const

const exportButton = (w: ReturnType<typeof mount>) => {
  const found = w.findAll('button').filter((b) => /Export/.test(b.text()))
  expect(found).toHaveLength(1)
  return found[0]!
}

beforeEach(() => {
  setActivePinia(createPinia())
  const clusters = useClusterStore()
  clusters.clusters = [{ cluster_id: CLUSTER, cluster_name: 'k3d' }] as never
  clusters.selectedId = CLUSTER
  clusters.loaded = true
  // Contributors and Running images draw their export button only after a read that succeeds
  // (Contributors needs one row: an empty board shows its empty state instead)
  const ok = (data: unknown) => ({ data, request: {}, response: { ok: true, status: 200 } }) as never
  const row = { actor: 'ana', actions: 1, by_action: { resolve: 1 }, handled: 1, median_ttr_seconds: null, sla_hit_pct: null }
  vi.mocked(contributorsApiV1ContributorsGet).mockResolvedValue(
    ok({ leaderboard: [row], handled_over_time: [], totals: null }),
  )
  const inventory = { inventory_run_id: 'r-1', inventory_order: 1, started_at: null, completed_at: null }
  vi.mocked(listRunningImagesApiV1ImagesGet).mockResolvedValue(ok({ inventory, images: [] }))
})

describe('a role without can_export sees the control, disabled, with the reason', () => {
  it.each(SCREENS)('%s', async (_name, screen, props) => {
    signIn(['can_triage', 'can_accept_audit_final'])
    const w = await mountRouted(screen as Component, props)
    const button = exportButton(w)
    expect(button.attributes('disabled')).toBeDefined()
    const note = w.find('#no-export-note')
    expect(note.text()).toBe(NO_EXPORT_NOTE)
    expect(button.attributes('aria-describedby')).toBe('no-export-note')
  })
})

describe('a role with can_export gets the control as before, with no note', () => {
  it.each(SCREENS)('%s', async (_name, screen, props) => {
    signIn(['can_export', 'can_accept_audit_final'])
    const w = await mountRouted(screen as Component, props)
    const button = exportButton(w)
    expect(w.find('#no-export-note').exists()).toBe(false)
    expect(button.attributes('aria-describedby')).toBeUndefined()
  })

  it('admin, through "*"', async () => {
    signIn(['*'])
    const w = await mountRouted(ExportDialog as Component, SCREENS[0][2])
    expect(exportButton(w).attributes('disabled')).toBeUndefined()
    expect(w.find('#no-export-note').exists()).toBe(false)
  })
})

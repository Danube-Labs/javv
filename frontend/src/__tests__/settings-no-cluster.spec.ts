/**
 * Per-cluster settings before any cluster is listed (issue 817, finding 3). Scan scope, Scanning
 * and the settings of Data & OpenSearch read with a cluster id; on a fresh install there is none,
 * and each sat on its loading placeholder for good. They now say why and where to go instead.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { Component } from 'vue'

import * as sdk from '@/api/generated'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import DataOpenSearchView from '@/views/settings/DataOpenSearchView.vue'
import ScanningView from '@/views/settings/ScanningView.vue'
import ScanScopeView from '@/views/settings/ScanScopeView.vue'

vi.mock('@/api/generated', async (importOriginal) => {
  const pending = () => new Promise<never>(() => {}) // a read still in flight
  return (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
    getScanScopeSessionApiV1SettingsScanScopeGet: vi.fn<() => Promise<unknown>>(pending),
    getStalenessApiV1SettingsStalenessGet: vi.fn<() => Promise<unknown>>(pending),
    scannerProvenanceApiV1ScannersProvenanceGet: vi.fn<() => Promise<unknown>>(pending),
    getDataSettingsApiV1SettingsDataGet: vi.fn<() => Promise<unknown>>(pending),
    listSnapshotsApiV1AdminSnapshotsGet: vi.fn<() => Promise<unknown>>(pending),
    getOpensearchRuntimeApiV1AdminOpensearchRuntimeGet: vi.fn<() => Promise<unknown>>(pending),
  })
})

const VIEWS: [string, Component, () => unknown][] = [
  ['Scan scope', ScanScopeView, () => sdk.getScanScopeSessionApiV1SettingsScanScopeGet],
  ['Scanning', ScanningView, () => sdk.getStalenessApiV1SettingsStalenessGet],
  ['Data & OpenSearch', DataOpenSearchView, () => sdk.getDataSettingsApiV1SettingsDataGet],
]

async function withClusters(ids: string[]) {
  useAuthStore().user = { username: 'admin', capabilities: ['can_manage_settings'] } as never
  vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue({
    response: { ok: true },
    data: { clusters: ids.map((cluster_id) => ({ cluster_id, cluster_name: cluster_id })) },
  } as never)
  await useClusterStore().fetchClusters(null)
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe.each(VIEWS)('%s with no cluster listed', (_name, view, read) => {
  it('says settings come with the first token, and sends no read', async () => {
    await withClusters([])
    const w = mount(view)
    await flushPromises()
    expect(w.text()).toContain('Settings for a cluster appear once it has a scanner token.')
    expect(w.text()).toContain('Mint one under Access & tokens.')
    expect(w.find('.skel').exists()).toBe(false)
    expect(read()).not.toHaveBeenCalled()
  })
})

describe.each(VIEWS)('%s with a cluster listed', (_name, view, read) => {
  it('reads that cluster and shows its loading state, not the empty one', async () => {
    await withClusters(['alpha'])
    const w = mount(view)
    await flushPromises()
    expect(read()).toHaveBeenCalledWith(expect.objectContaining({ query: expect.objectContaining({ cluster_id: 'alpha' }) }))
    expect(w.text()).not.toContain('Settings for a cluster appear')
    expect(w.find('.skel').exists()).toBe(true)
  })
})

it('the cluster list failing is not "no cluster": the shell reports that failure', async () => {
  vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue({ response: { ok: false, status: 503 } } as never)
  await useClusterStore().fetchClusters(null)
  expect(useClusterStore().none).toBe(false)
  const w = mount(ScanScopeView)
  await flushPromises()
  expect(w.text()).not.toContain('Settings for a cluster appear')
})

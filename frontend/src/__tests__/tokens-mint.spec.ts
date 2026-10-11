/**
 * Minting a token for a cluster JAVV has not seen yet (issue 817, finding 1). A cluster is listed
 * once its first token exists, so a fresh install has nothing to pick: the mint dialog offers
 * "New cluster…", which takes a typed cluster ID checked against the backend's own rule.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as sdk from '@/api/generated'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import TokensView from '@/views/settings/TokensView.vue'
import { CLUSTER_ID, mintClusterId, NEW_CLUSTER } from '@/views/settings/tokensForm'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
    listTokensApiV1AdminTokensGet: vi.fn<() => Promise<unknown>>(),
    mintApiV1AdminTokensPost: vi.fn<() => Promise<unknown>>(),
  }),
)

const UID = '4f0c2a9e-71d3-4b8e-9a51-0c6e2d7f3b18'

describe('mintClusterId', () => {
  it('passes a picked cluster through', () => {
    expect(mintClusterId('alpha', '')).toBe('alpha')
    expect(mintClusterId('', '')).toBeNull()
  })

  it('takes the typed id for a new cluster, trimmed, once it is well-formed', () => {
    expect(mintClusterId(NEW_CLUSTER, `  ${UID} `)).toBe(UID)
    expect(mintClusterId(NEW_CLUSTER, '')).toBeNull()
    expect(mintClusterId(NEW_CLUSTER, 'My-Cluster')).toBeNull() // uppercase
    expect(mintClusterId(NEW_CLUSTER, '-abcdefgh')).toBeNull() // leading dash
    expect(mintClusterId(NEW_CLUSTER, 'abcdefg')).toBeNull() // 7 characters
    expect(mintClusterId(NEW_CLUSTER, 'a'.repeat(64))).toBe('a'.repeat(64))
    expect(mintClusterId(NEW_CLUSTER, 'a'.repeat(65))).toBeNull()
  })

  it('never takes the choice marker for a cluster id', () => {
    expect(CLUSTER_ID.test(NEW_CLUSTER)).toBe(false)
  })

  it('is the server rule: the pattern equals the backend one', () => {
    const source = readFileSync(resolve(process.cwd(), '..', 'backend/src/backend/core/identifiers.py'), 'utf8')
    expect(/^CLUSTER_ID_RE = re\.compile\(r"(.+)"\)$/m.exec(source)?.[1]).toBe(CLUSTER_ID.source)
  })
})

describe('the mint dialog', () => {
  const row = (cluster_id: string) => ({
    cluster_id,
    cluster_name: cluster_id,
    retired: false,
    last_scan_at: null,
    silent_since: null,
    warns_at: null,
    retires_at: null,
    delete_started: false,
    retirement_mode: null,
  })
  let listed: ReturnType<typeof row>[] = []

  async function mountTokens(clusters: string[]) {
    useAuthStore().user = { username: 'admin', capabilities: ['can_manage_tokens'] } as never
    listed = clusters.map(row)
    vi.mocked(sdk.listClustersApiV1ClustersGet).mockImplementation((async () => ({
      response: { ok: true },
      data: { clusters: listed },
    })) as never)
    vi.mocked(sdk.listTokensApiV1AdminTokensGet).mockResolvedValue({
      response: { ok: true },
      data: { total: 0, tokens: [] },
    } as never)
    await useClusterStore().fetchClusters(null)
    const w = mount(TokensView)
    await flushPromises()
    await w.findAll('button').find((b) => b.text().startsWith('Mint token'))!.trigger('click')
    await flushPromises()
    return w
  }
  const mintButton = (w: ReturnType<typeof mount>) =>
    w.findAll('.modal-actions button').find((b) => b.text().startsWith('Mint'))!

  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('on a fresh install, opens on a new cluster with the ID field and the command', async () => {
    const w = await mountTokens([])
    expect(w.findAll('select#mint-cluster option').map((o) => o.text())).toEqual(['New cluster…'])
    expect((w.get('select#mint-cluster').element as HTMLSelectElement).value).toBe(NEW_CLUSTER)
    expect(w.get('label[for="mint-cluster-id"]').text()).toContain('Cluster ID')
    expect(w.text()).toContain("kubectl get namespace kube-system -o jsonpath='{.metadata.uid}'")
    expect(mintButton(w).attributes('disabled')).toBeDefined()
    expect(w.find('.modal-error').exists()).toBe(false) // empty is unfinished, not wrong
  })

  it('names a malformed id and keeps Mint off', async () => {
    const w = await mountTokens([])
    await w.get('#mint-cluster-id').setValue('My-Cluster')
    expect(w.get('.modal-error').text()).toMatch(/8 to 64 characters: lowercase letters, digits and dashes/)
    expect(w.get('#mint-cluster-id').attributes('aria-invalid')).toBe('true')
    expect(mintButton(w).attributes('disabled')).toBeDefined()
  })

  it('mints for the typed id, then lists the new cluster without a reload', async () => {
    vi.mocked(sdk.mintApiV1AdminTokensPost).mockImplementation((async () => {
      listed = [row(UID)] // the token is what lists the cluster
      return { response: { ok: true, status: 201 }, data: { id: 't1', token: 'raw' } }
    }) as never)
    const w = await mountTokens([])
    await w.get('#mint-cluster-id').setValue(UID)
    expect(mintButton(w).attributes('disabled')).toBeUndefined()
    await mintButton(w).trigger('click')
    await flushPromises()
    expect(sdk.mintApiV1AdminTokensPost).toHaveBeenCalledWith(
      expect.objectContaining({ body: { cluster_id: UID, scanner: 'trivy' } }),
    )
    expect(w.text()).toContain('Copy this token now')
    expect(useClusterStore().clusters.map((c) => c.cluster_id)).toEqual([UID])
    expect(useClusterStore().selectedId).toBe(UID)
  })

  it('with clusters listed, offers New cluster… after them and opens on the selected one', async () => {
    const w = await mountTokens(['alpha', 'beta'])
    expect(w.findAll('select#mint-cluster > option').map((o) => o.text())).toEqual([
      'alpha',
      'beta',
      'New cluster…',
    ])
    expect((w.get('select#mint-cluster').element as HTMLSelectElement).value).toBe('alpha')
    expect(w.find('#mint-cluster-id').exists()).toBe(false)
    await w.get('select#mint-cluster').setValue(NEW_CLUSTER)
    expect(w.find('#mint-cluster-id').exists()).toBe(true)
  })

  it('minting for a listed cluster does not re-read the cluster list', async () => {
    vi.mocked(sdk.mintApiV1AdminTokensPost).mockResolvedValue({
      response: { ok: true, status: 201 },
      data: { id: 't1', token: 'raw' },
    } as never)
    const w = await mountTokens(['alpha'])
    const reads = vi.mocked(sdk.listClustersApiV1ClustersGet).mock.calls.length
    await mintButton(w).trigger('click')
    await flushPromises()
    expect(sdk.mintApiV1AdminTokensPost).toHaveBeenCalledWith(
      expect.objectContaining({ body: { cluster_id: 'alpha', scanner: 'trivy' } }),
    )
    expect(vi.mocked(sdk.listClustersApiV1ClustersGet).mock.calls.length).toBe(reads)
  })
})

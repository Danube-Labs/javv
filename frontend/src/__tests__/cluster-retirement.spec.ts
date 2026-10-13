/**
 * Cluster retirement in Settings (issue 765): what the retirement window editor refuses before it
 * ever reaches the backend (which refuses the same things with a 422), and the Cluster panel's
 * retire, bring back and delete controls against a mocked SDK.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as sdk from '@/api/generated'
import ClusterDeleteDialog from '@/components/settings/ClusterDeleteDialog.vue'
import RetiredClustersCard from '@/components/settings/RetiredClustersCard.vue'
import RetirementWindowCard from '@/components/settings/RetirementWindowCard.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import ClusterView from '@/views/settings/ClusterView.vue'
import TokensView from '@/views/settings/TokensView.vue'
import { windowProblem } from '@/views/settings/retirementForm'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
    retireApiV1ClustersClusterIdRetirePost: vi.fn<() => Promise<unknown>>(),
    unretireApiV1ClustersClusterIdUnretirePost: vi.fn<() => Promise<unknown>>(),
    deleteRetiredClusterApiV1ClustersClusterIdDelete: vi.fn<() => Promise<unknown>>(),
    getRetirementApiV1SettingsRetirementGet: vi.fn<() => Promise<unknown>>(),
    putRetirementApiV1SettingsRetirementPut: vi.fn<() => Promise<unknown>>(),
    getStalenessApiV1SettingsStalenessGet: vi.fn<() => Promise<unknown>>(),
    listTokensApiV1AdminTokensGet: vi.fn<() => Promise<unknown>>(),
    mintApiV1AdminTokensPost: vi.fn<() => Promise<unknown>>(),
  }),
)

describe('windowProblem', () => {
  it('accepts a window past the scanner-down timer with a shorter warning', () => {
    expect(windowProblem('after', 45, 7, 7)).toBeNull()
  })

  it('accepts never with any positive warning', () => {
    expect(windowProblem('never', null, 7, 7)).toBeNull()
  })

  it('refuses a window not longer than the scanner-down timer, naming it, on the window', () => {
    expect(windowProblem('after', 7, 2, 7)).toEqual({
      field: 'after',
      message: expect.stringMatching(/longer than the scanner-down timer \(7 days\)/),
    })
  })

  it('leaves the scanner-down check to the backend while that timer is unknown', () => {
    expect(windowProblem('after', 5, 2, null)).toBeNull()
  })

  it('refuses a warning as long as the window, on the warning', () => {
    expect(windowProblem('after', 30, 30, 7)).toEqual({
      field: 'warn',
      message: expect.stringMatching(/shorter than the retirement window/),
    })
  })

  it('refuses empty or non-positive values, on the field that holds them', () => {
    expect(windowProblem('after', null, 7, 7)?.field).toBe('after')
    expect(windowProblem('after', 45, null, 7)?.field).toBe('warn')
  })
})

const fleetRow = (
  cluster_id: string,
  retired: boolean,
  cluster_name = cluster_id,
  extra: { delete_started?: boolean; retirement_mode?: 'manual' | 'auto' | null } = {},
) => ({
  cluster_id,
  cluster_name,
  retired,
  last_scan_at: '2026-08-01T00:00:00+00:00',
  silent_since: '2026-08-01T00:00:00+00:00',
  warns_at: null,
  retires_at: null,
  delete_started: false,
  retirement_mode: (retired ? 'auto' : null) as 'manual' | 'auto' | null,
  ...extra,
})

/** The listing as the backend serves it: retired clusters only with `include_retired`. */
function listing(rows: ReturnType<typeof fleetRow>[]) {
  vi.mocked(sdk.listClustersApiV1ClustersGet).mockImplementation((async (opts?: {
    query?: { include_retired?: boolean }
  }) => ({
    response: { ok: true },
    data: { clusters: opts?.query?.include_retired ? rows : rows.filter((r) => !r.retired) },
  })) as never)
}

function signIn(capabilities: string[]) {
  useAuthStore().user = { username: 'admin', capabilities } as never
}

const ok = { response: { ok: true, status: 200 }, data: {} } as never
const status = (code: number) => ({ response: { ok: false, status: code }, data: undefined }) as never

const buttons = (w: ReturnType<typeof mount>, text: string) =>
  w.findAll('button').filter((b) => b.text().startsWith(text))

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
})

describe('RetiredClustersCard', () => {
  it('lists only the retired clusters', async () => {
    signIn(['can_manage_settings'])
    listing([fleetRow('alpha', false), fleetRow('beta', true, 'Beta prod')])
    const w = mount(RetiredClustersCard)
    await flushPromises()
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.text()).toContain('Beta prod')
    expect(rows[0]!.text()).toContain('beta')
  })

  it('names a never-renamed cluster by its id once, not twice', async () => {
    signIn(['can_manage_settings'])
    listing([fleetRow('c-old-01', true)]) // no registry name: the listing names it by its id
    const w = mount(RetiredClustersCard)
    await flushPromises()
    expect(w.find('tbody .name-cell').text()).toBe('c-old-01')
    expect(w.find('tbody .id-cell').exists()).toBe(false)
  })

  it('shows Delete only with can_manage_retention', async () => {
    listing([fleetRow('beta', true)])
    signIn(['can_manage_settings'])
    const without = mount(RetiredClustersCard)
    await flushPromises()
    expect(buttons(without, 'Delete')).toHaveLength(0)
    expect(buttons(without, 'Bring back')).toHaveLength(1)

    signIn(['can_manage_settings', 'can_manage_retention'])
    const withCap = mount(RetiredClustersCard)
    await flushPromises()
    expect(buttons(withCap, 'Delete')).toHaveLength(1)
  })

  it('Bring back un-retires that cluster and reloads the list', async () => {
    signIn(['can_manage_settings'])
    listing([fleetRow('beta', true)])
    vi.mocked(sdk.unretireApiV1ClustersClusterIdUnretirePost).mockResolvedValue(ok)
    const w = mount(RetiredClustersCard)
    await flushPromises()
    listing([fleetRow('beta', false)])
    await buttons(w, 'Bring back')[0]!.trigger('click')
    await flushPromises()
    expect(sdk.unretireApiV1ClustersClusterIdUnretirePost).toHaveBeenCalledWith(
      expect.objectContaining({ path: { cluster_id: 'beta' } }),
    )
    expect(w.findAll('tbody tr')).toHaveLength(0)
    expect(w.text()).toContain('No retired clusters')
    // the switcher's list too, so it is selectable at once
    expect(useClusterStore().clusters.map((c) => c.cluster_id)).toEqual(['beta'])
  })
})

describe('RetiredClustersCard, issue 778', () => {
  const toasts = async () => JSON.stringify((await import('@/stores/toast')).useToastStore().$state)

  it('offers only Delete for a cluster whose delete did not finish', async () => {
    signIn(['can_manage_settings', 'can_manage_retention'])
    listing([fleetRow('beta', true, 'beta', { delete_started: true }), fleetRow('gamma', true)])
    const w = mount(RetiredClustersCard)
    await flushPromises()
    const [beta, gamma] = w.findAll('tbody tr')
    expect(beta!.findAll('button').map((b) => b.text())).toEqual(['Delete…'])
    expect(beta!.text()).toContain('Its delete did not finish. Delete it again.')
    expect(gamma!.findAll('button').map((b) => b.text())).toEqual(['Bring back', 'Delete…'])
    expect(gamma!.text()).not.toContain('did not finish')
  })

  it('tells an admin who cannot delete that someone who can must finish it', async () => {
    signIn(['can_manage_settings'])
    listing([fleetRow('beta', true, 'beta', { delete_started: true })])
    const w = mount(RetiredClustersCard)
    await flushPromises()
    const row = w.find('tbody tr')
    expect(row.findAll('button')).toHaveLength(0)
    expect(row.text()).toContain(
      'Its delete did not finish. Someone who can delete clusters must delete it again.',
    )
  })

  it('after bringing back a manual retire, says its scanners need a new token', async () => {
    signIn(['can_manage_settings'])
    listing([fleetRow('beta', true, 'beta', { retirement_mode: 'manual' })])
    vi.mocked(sdk.unretireApiV1ClustersClusterIdUnretirePost).mockResolvedValue(ok)
    const w = mount(RetiredClustersCard)
    await flushPromises()
    await buttons(w, 'Bring back')[0]!.trigger('click')
    await flushPromises()
    expect(await toasts()).toContain(
      'beta is back on the cluster list. Its tokens were revoked when it was retired: mint a new one for its scanners.',
    )
  })

  it('after bringing back an automatic retire, does not ask for a token', async () => {
    signIn(['can_manage_settings'])
    listing([fleetRow('beta', true, 'beta', { retirement_mode: 'auto' })])
    vi.mocked(sdk.unretireApiV1ClustersClusterIdUnretirePost).mockResolvedValue(ok)
    const w = mount(RetiredClustersCard)
    await flushPromises()
    await buttons(w, 'Bring back')[0]!.trigger('click')
    await flushPromises()
    expect(await toasts()).toContain('beta is back on the cluster list')
    expect(await toasts()).not.toContain('token')
  })

  it('says so when a delete started after the list was read', async () => {
    signIn(['can_manage_settings'])
    listing([fleetRow('beta', true)])
    vi.mocked(sdk.unretireApiV1ClustersClusterIdUnretirePost).mockResolvedValue({
      response: { ok: false, status: 409 },
      // matched on the type: a reworded title must not turn this into "not retired any more"
      error: { type: 'cluster-delete-unfinished', title: 'a reworded title' },
      data: undefined,
    } as never)
    const w = mount(RetiredClustersCard)
    await flushPromises()
    await buttons(w, 'Bring back')[0]!.trigger('click')
    await flushPromises()
    expect(await toasts()).toContain('Its delete did not finish. Delete it again.')
  })

  it('says it is not retired any more for a 409 without that type', async () => {
    signIn(['can_manage_settings'])
    listing([fleetRow('beta', true)])
    vi.mocked(sdk.unretireApiV1ClustersClusterIdUnretirePost).mockResolvedValue({
      response: { ok: false, status: 409 },
      error: { type: 'about:blank', title: 'cluster is not retired' },
      data: undefined,
    } as never)
    const w = mount(RetiredClustersCard)
    await flushPromises()
    await buttons(w, 'Bring back')[0]!.trigger('click')
    await flushPromises()
    expect(await toasts()).toContain('It is not retired any more.')
    expect(await toasts()).not.toContain('delete')
  })
})

describe('RetiredClustersCard after a 409 delete', () => {
  it('reloads the list: the cluster was brought back meanwhile', async () => {
    signIn(['can_manage_settings', 'can_manage_retention'])
    listing([fleetRow('beta', true)])
    vi.mocked(sdk.deleteRetiredClusterApiV1ClustersClusterIdDelete).mockResolvedValue(status(409))
    const w = mount(RetiredClustersCard)
    await flushPromises()
    await buttons(w, 'Delete')[0]!.trigger('click')
    listing([fleetRow('beta', false)])
    await w.find('input#delete-confirm').setValue('beta')
    await buttons(w, 'Delete cluster')[0]!.trigger('click')
    await flushPromises()
    expect(w.findAll('tbody tr')).toHaveLength(0)
  })
})

describe('ClusterDeleteDialog', () => {
  const mountDialog = () =>
    mount(ClusterDeleteDialog, { props: { clusterId: 'c-beta-01', clusterName: 'beta' } })
  const deleteButton = (w: ReturnType<typeof mount>) => buttons(w, 'Delete cluster')[0]!

  it('keeps Delete disabled until the name is typed exactly', async () => {
    const w = mountDialog()
    expect(deleteButton(w).attributes('disabled')).toBeDefined()
    await w.find('input#delete-confirm').setValue('bet')
    expect(deleteButton(w).attributes('disabled')).toBeDefined()
    await w.find('input#delete-confirm').setValue('beta')
    expect(deleteButton(w).attributes('disabled')).toBeUndefined()
  })

  it('deletes by the cluster id and reports done', async () => {
    vi.mocked(sdk.deleteRetiredClusterApiV1ClustersClusterIdDelete).mockResolvedValue(ok)
    const w = mountDialog()
    await w.find('input#delete-confirm').setValue('beta')
    await deleteButton(w).trigger('click')
    await flushPromises()
    expect(sdk.deleteRetiredClusterApiV1ClustersClusterIdDelete).toHaveBeenCalledWith(
      expect.objectContaining({ path: { cluster_id: 'c-beta-01' } }),
    )
    expect(w.emitted('deleted')).toHaveLength(1)
  })

  it.each([
    [503, /Delete it again to finish it/],
    [409, /not retired any more/],
    [403, /needs the can_manage_retention capability/],
    [500, /Deleting failed/],
  ])('a %i says what to do and keeps the dialog open', async (code, message) => {
    vi.mocked(sdk.deleteRetiredClusterApiV1ClustersClusterIdDelete).mockResolvedValue(status(code))
    const w = mountDialog()
    await w.find('input#delete-confirm').setValue('beta')
    await deleteButton(w).trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toMatch(message)
    expect(w.emitted('deleted')).toBeUndefined()
    // the list is stale only when the cluster changed under it
    expect(w.emitted('changed')?.length ?? 0).toBe(code === 409 ? 1 : 0)
  })

  it('a 404 means it is already deleted: done, as a success', async () => {
    vi.mocked(sdk.deleteRetiredClusterApiV1ClustersClusterIdDelete).mockResolvedValue(status(404))
    const w = mountDialog()
    await w.find('input#delete-confirm').setValue('beta')
    await deleteButton(w).trigger('click')
    await flushPromises()
    expect(w.emitted('deleted')).toHaveLength(1)
  })

  it('cannot be closed while the delete runs, so its outcome is never dropped', async () => {
    let finish: (v: unknown) => void = () => {}
    vi.mocked(sdk.deleteRetiredClusterApiV1ClustersClusterIdDelete).mockReturnValue(
      new Promise((resolve) => (finish = resolve)) as never,
    )
    const w = mountDialog()
    await w.find('input#delete-confirm').setValue('beta')
    await deleteButton(w).trigger('click')
    expect(buttons(w, 'Cancel')[0]!.attributes('disabled')).toBeDefined()
    await w.find('button[aria-label="Close"]').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toBeUndefined()
    finish(ok)
    await flushPromises()
    expect(w.emitted('deleted')).toHaveLength(1)
    w.unmount()
  })

  it('lists reports and notifications among what goes', () => {
    expect(mountDialog().text()).toContain('its reports and notifications')
  })
})

describe('RetirementWindowCard', () => {
  function stored(retire_after_days: number | null, per_cluster_override: boolean) {
    vi.mocked(sdk.getRetirementApiV1SettingsRetirementGet).mockResolvedValue({
      response: { ok: true },
      data: { retirement: { retire_after_days, warn_days: 7 }, per_cluster_override },
    } as never)
  }

  // the fleet's scanner-down timer is 7 days, alpha's own override is 10
  async function mountCard() {
    vi.mocked(sdk.getStalenessApiV1SettingsStalenessGet).mockImplementation((async (opts?: {
      query?: { cluster_id?: string }
    }) => ({
      response: { ok: true },
      data: { staleness: { freshness_days: 3, scanner_down_days: opts?.query?.cluster_id ? 10 : 7 } },
    })) as never)
    useClusterStore().selectedId = 'alpha'
    const w = mount(RetirementWindowCard)
    await flushPromises()
    return w
  }

  const putBody = () =>
    (vi.mocked(sdk.putRetirementApiV1SettingsRetirementPut).mock.calls[0]![0] as { body: unknown }).body

  async function saveWith(w: ReturnType<typeof mount>, after: string | null, warn: string) {
    if (after === null) await buttons(w, 'Never')[0]!.trigger('click')
    else await w.find('input#retire-after').setValue(after)
    await w.find('input#retire-warn').setValue(warn)
    await buttons(w, 'Save')[0]!.trigger('click')
    await flushPromises()
  }

  it('checks an override against the cluster’s own scanner-down timer', async () => {
    stored(45, true)
    const w = await mountCard()
    expect(w.text()).toContain('longer than the scanner-down timer (10 days)')
  })

  it('checks the fleet default against the fleet’s scanner-down timer, as the backend does', async () => {
    stored(45, false)
    const w = await mountCard()
    expect(w.text()).toContain('longer than the scanner-down timer (7 days)')
  })

  it('saves an override with the cluster id, and the fleet default without one', async () => {
    vi.mocked(sdk.putRetirementApiV1SettingsRetirementPut).mockResolvedValue(ok)
    stored(45, true)
    await saveWith(await mountCard(), '60', '5')
    expect(putBody()).toEqual({ retire_after_days: 60, warn_days: 5, cluster_id: 'alpha' })

    vi.clearAllMocks()
    setActivePinia(createPinia())
    vi.mocked(sdk.putRetirementApiV1SettingsRetirementPut).mockResolvedValue(ok)
    stored(45, false)
    await saveWith(await mountCard(), null, '5')
    expect(putBody()).toEqual({ retire_after_days: null, warn_days: 5 })
  })

  it('shows the backend’s reason when it refuses the window', async () => {
    vi.mocked(sdk.putRetirementApiV1SettingsRetirementPut).mockResolvedValue({
      response: { ok: false, status: 422 },
      error: { title: 'the retirement window must be longer than the scanner-down timer (9 days)' },
    } as never)
    stored(45, false)
    const w = await mountCard()
    await saveWith(w, '60', '5')
    const { useToastStore } = await import('@/stores/toast')
    expect(JSON.stringify(useToastStore().$state)).toContain(
      'The retirement window must be longer than the scanner-down timer (9 days). The sweep keeps',
    )
  })

  it('is clean until a value changes, and a reformatted value stays clean', async () => {
    stored(45, false)
    const w = await mountCard()
    const save = () => buttons(w, 'Save')[0]
    expect(save()?.attributes('disabled')).toBeDefined()
    await w.find('input#retire-after').setValue('45.0')
    expect(save()?.attributes('disabled')).toBeDefined()
    await w.find('input#retire-after').setValue('50')
    expect(save()?.attributes('disabled')).toBeUndefined()
  })

  it('a save that lands after a cluster switch leaves the new cluster’s form alone', async () => {
    let answerPut: (v: unknown) => void = () => {}
    vi.mocked(sdk.putRetirementApiV1SettingsRetirementPut).mockReturnValue(
      new Promise((resolve) => (answerPut = resolve)) as never,
    )
    stored(45, false)
    const w = await mountCard()
    await saveWith(w, '60', '5')
    stored(90, false)
    useClusterStore().selectedId = 'beta'
    await flushPromises()
    answerPut(ok)
    await flushPromises()
    // beta's saved values are still beta's own: its form is clean
    expect((w.find('input#retire-after').element as HTMLInputElement).value).toBe('90')
    expect(buttons(w, 'Save')[0]?.attributes('disabled')).toBeDefined()
  })

  it('drops a slow answer for a cluster that is no longer selected', async () => {
    let answerAlpha: (v: unknown) => void = () => {}
    vi.mocked(sdk.getRetirementApiV1SettingsRetirementGet).mockImplementation((async (opts: {
      query: { cluster_id?: string }
    }) =>
      opts.query.cluster_id === 'alpha'
        ? new Promise((resolve) => (answerAlpha = resolve))
        : {
            response: { ok: true },
            data: { retirement: { retire_after_days: 90, warn_days: 9 }, per_cluster_override: false },
          }) as never)
    const w = await mountCard()
    useClusterStore().selectedId = 'beta'
    await flushPromises()
    answerAlpha({
      response: { ok: true },
      data: { retirement: { retire_after_days: 20, warn_days: 3 }, per_cluster_override: true },
    })
    await flushPromises()
    expect((w.find('input#retire-after').element as HTMLInputElement).value).toBe('90')
    expect(w.text()).toContain('Editing the fleet-wide default')
  })

  it('never hides the days input', async () => {
    stored(null, false)
    const w = await mountCard()
    expect(w.find('input#retire-after').exists()).toBe(false)
    expect(w.find('input#retire-warn').exists()).toBe(true)
  })

  it('says whether it edits this cluster’s override or the fleet default', async () => {
    stored(45, true)
    expect((await mountCard()).text()).toContain('Editing THIS cluster')
    setActivePinia(createPinia())
    stored(45, false)
    expect((await mountCard()).text()).toContain('Editing the fleet-wide default')
  })
})

describe('ClusterView retire', () => {
  async function mountView() {
    signIn(['can_manage_settings'])
    listing([fleetRow('alpha', false)])
    vi.mocked(sdk.getRetirementApiV1SettingsRetirementGet).mockResolvedValue({
      response: { ok: true },
      data: { retirement: { retire_after_days: 45, warn_days: 7 }, per_cluster_override: false },
    } as never)
    vi.mocked(sdk.getStalenessApiV1SettingsStalenessGet).mockResolvedValue({
      response: { ok: true },
      data: { staleness: { freshness_days: 3, scanner_down_days: 7 } },
    } as never)
    const store = useClusterStore()
    await store.fetchClusters('alpha')
    const w = mount(ClusterView)
    await flushPromises()
    return w
  }

  it('asks before retiring, and says a scan on a new token brings it back', async () => {
    const w = await mountView()
    await buttons(w, 'Retire cluster…')[0]!.trigger('click')
    expect(w.text()).toContain('the first scan on a new token brings it')
    expect(sdk.retireApiV1ClustersClusterIdRetirePost).not.toHaveBeenCalled()
  })

  it('a refused retire says why and leaves the cluster listed', async () => {
    vi.mocked(sdk.retireApiV1ClustersClusterIdRetirePost).mockResolvedValue(status(409))
    const w = await mountView()
    await buttons(w, 'Retire cluster…')[0]!.trigger('click')
    await buttons(w, 'Retire cluster').find((b) => b.text() === 'Retire cluster')!.trigger('click')
    await flushPromises()
    const { useToastStore } = await import('@/stores/toast')
    expect(JSON.stringify(useToastStore().$state)).toContain('It is already retired.')
    expect(useClusterStore().clusters.map((c) => c.cluster_id)).toEqual(['alpha'])
  })

  it('retires the selected cluster on confirm, and it leaves the switcher', async () => {
    vi.mocked(sdk.retireApiV1ClustersClusterIdRetirePost).mockResolvedValue(ok)
    const w = await mountView()
    listing([fleetRow('alpha', true), fleetRow('beta', false)])
    await buttons(w, 'Retire cluster…')[0]!.trigger('click')
    await buttons(w, 'Retire cluster').find((b) => b.text() === 'Retire cluster')!.trigger('click')
    await flushPromises()
    expect(sdk.retireApiV1ClustersClusterIdRetirePost).toHaveBeenCalledWith(
      expect.objectContaining({ path: { cluster_id: 'alpha' } }),
    )
    expect(useClusterStore().clusters.map((c) => c.cluster_id)).toEqual(['beta'])
    expect(useClusterStore().selectedId).toBe('beta')
    // one toast: the retire says what happened, the re-read does not repeat it
    const { useToastStore } = await import('@/stores/toast')
    expect(JSON.stringify(useToastStore().$state)).not.toContain('no longer on the cluster list')
  })
})

describe('minting for a retired cluster', () => {
  async function mountTokens(extra: ReturnType<typeof fleetRow>[] = []) {
    signIn(['can_manage_tokens'])
    listing([fleetRow('alpha', false), fleetRow('c-old-01', true, 'old'), ...extra])
    vi.mocked(sdk.listTokensApiV1AdminTokensGet).mockResolvedValue({
      response: { ok: true },
      data: {
        total: 1,
        tokens: [
          {
            id: 't1',
            cluster_id: 'c-old-01',
            scanner: 'trivy',
            scope: 'push:findings',
            created_by: 'admin',
            created_at: '2026-08-01T00:00:00+00:00',
            expiry: null,
            disabled: true,
            last_ingest_at: null,
          },
        ],
      },
    } as never)
    await useClusterStore().fetchClusters('alpha')
    // retired since the app loaded: the app-load list still has it
    useClusterStore().clusters.push({ cluster_id: 'c-old-01', cluster_name: 'old' })
    const w = mount(TokensView)
    await flushPromises()
    return w
  }

  it('does not offer a cluster whose delete did not finish (issue 778)', async () => {
    const w = await mountTokens([fleetRow('c-half-01', true, 'half', { delete_started: true })])
    await buttons(w, 'Mint token')[0]!.trigger('click')
    await flushPromises()
    const retired = w.findAll('select#mint-cluster optgroup option').map((o) => o.text())
    expect(retired).toEqual(['old (retired)'])
  })

  it('names a retired cluster’s tokens instead of showing its id', async () => {
    const w = await mountTokens()
    expect(w.find('tbody .cluster-cell').text()).toBe('old')
  })

  it('lists retired clusters apart, and says a scan on the new token brings one back', async () => {
    vi.mocked(sdk.mintApiV1AdminTokensPost).mockResolvedValue({
      response: { ok: true, status: 200 },
      data: { id: 't2', token: 'raw' },
    } as never)
    const w = await mountTokens()
    await buttons(w, 'Mint token')[0]!.trigger('click')
    await flushPromises()
    // both groups come from the one fresh listing, never the app-load list
    const active = w.findAll('select#mint-cluster > option').map((o) => o.text())
    expect(active).toEqual(['alpha', 'New cluster…'])
    const group = w.find('select#mint-cluster optgroup')
    expect(group.attributes('label')).toBe('Retired')
    expect(group.findAll('option').map((o) => o.text())).toEqual(['old (retired)'])
    expect(w.text()).not.toContain('is retired. Its first scan')

    await w.find('select#mint-cluster').setValue('c-old-01')
    expect(w.text()).toContain('old is retired. Its first scan on this token brings it back')
    await buttons(w, 'Mint token').at(-1)!.trigger('click')
    await flushPromises()
    expect(sdk.mintApiV1AdminTokensPost).toHaveBeenCalledWith(
      expect.objectContaining({ body: expect.objectContaining({ cluster_id: 'c-old-01' }) }),
    )
  })
})

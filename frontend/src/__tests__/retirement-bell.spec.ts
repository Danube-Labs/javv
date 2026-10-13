/**
 * The retirement bell row (issue 765): a `cluster_retiring` notification names the cluster (a
 * retired one by the name the feed carries, issue 787) and the date it is due to be retired (or
 * that it is held past it), and opens Settings › Cluster for that cluster after re-reading the
 * list, or says it is gone. Either way the drawer closes.
 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import * as sdk from '@/api/generated'
import NotificationBell from '@/components/chrome/NotificationBell.vue'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
    listNotificationsApiV1NotificationsGet: vi.fn<() => Promise<unknown>>(),
    markReadApiV1NotificationsNotificationIdReadPatch: vi.fn<() => Promise<unknown>>(),
  }),
)

// midday, so the day shown is the same in every time zone between UTC-11 and UTC+11
const NOW = new Date('2026-10-08T12:00:00Z')
const DUE = '2026-10-14T12:00:00+00:00'

const notice = (cluster_id: string, ref = DUE, read = false, cluster_name: string | null = cluster_id) => ({
  notification_id: 'n1',
  type: 'cluster_retiring',
  ref,
  cluster_id,
  cluster_name,
  created_at: '2026-10-07T12:00:00+00:00',
  read,
})

const ALPHA = { cluster_id: 'c-alpha', cluster_name: 'alpha' }
const BETA = { cluster_id: 'c-beta', cluster_name: 'beta' }

/** What the re-read before the click returns. */
function listing(clusters: object[]) {
  vi.mocked(sdk.listClustersApiV1ClustersGet).mockResolvedValue({
    response: { ok: true, status: 200 },
    data: { clusters },
  } as never)
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/settings/cluster', name: 'settings-cluster', component: { template: '<div />' } },
    ],
  })
}

let mounted: VueWrapper | null = null

async function openBell(item: ReturnType<typeof notice>) {
  vi.mocked(sdk.listNotificationsApiV1NotificationsGet).mockResolvedValue({
    response: { ok: true, status: 200 },
    data: { unread: item.read ? 0 : 1, items: [item] },
  } as never)
  vi.mocked(sdk.markReadApiV1NotificationsNotificationIdReadPatch).mockResolvedValue({
    response: { ok: true, status: 200 },
    data: {},
  } as never)
  const router = makeRouter()
  const w = mount(NotificationBell, { global: { plugins: [router] }, attachTo: document.body })
  mounted = w
  await flushPromises()
  await w.find('button.bell-btn').trigger('click')
  await flushPromises()
  return { router }
}

const row = () => document.querySelector('.bell-row') as HTMLElement

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useClusterStore().clusters = [ALPHA, BETA]
  useClusterStore().loaded = true
  useClusterStore().selectedId = 'c-alpha'
  listing([ALPHA, BETA])
})

afterEach(() => {
  // a failed assertion skips the test's own unmount; the next test must not find its row
  mounted?.unmount()
  mounted = null
  vi.useRealTimers()
})

describe('the cluster_retiring bell row', () => {
  it('names the event, the cluster and the date it is due to be retired', async () => {
    await openBell(notice('c-beta'))
    expect(row().textContent).toContain('Cluster retiring')
    expect(row().textContent).toContain('beta is due to be retired on 14 Oct unless a scan arrives.')
  })

  it('says a cluster held past its date was due, not that it will be retired then', async () => {
    await openBell(notice('c-beta', '2026-10-01T12:00:00+00:00'))
    expect(row().textContent).toContain(
      'beta was due to be retired on 1 Oct and will be retired unless a scan arrives.',
    )
  })

  it('says a cluster retired since has been retired, by its name, not that it is due', async () => {
    // off the cluster list once retired: the name comes from the feed (issue 787)
    await openBell(notice('c-gone', '2026-10-01T12:00:00+00:00', false, 'payments-prod'))
    expect(row().textContent).toContain('payments-prod has been retired.')
    expect(row().textContent).not.toContain('c-gone')
    expect(row().textContent).not.toContain('due')
  })

  it('falls back to the id when the feed has no name', async () => {
    await openBell(notice('c-gone', '2026-10-01T12:00:00+00:00', false, null))
    expect(row().textContent).toContain('c-gone has been retired.')
  })

  it('opens Settings › Cluster with that cluster selected and closes the drawer', async () => {
    const { router } = await openBell(notice('c-beta'))
    row().click()
    await flushPromises()
    expect(useClusterStore().selectedId).toBe('c-beta')
    expect(router.currentRoute.value.name).toBe('settings-cluster')
    expect(sdk.markReadApiV1NotificationsNotificationIdReadPatch).toHaveBeenCalled()
    expect(document.querySelector('.bell-row')).toBeNull()
  })

  it('re-reads the list first: a cluster retired since the last poll is gone, and the drawer closes', async () => {
    const { router } = await openBell(notice('c-beta'))
    listing([ALPHA]) // the sweep retired beta after the list was loaded
    row().click()
    await flushPromises()
    expect(sdk.listClustersApiV1ClustersGet).toHaveBeenCalled()
    expect(useClusterStore().selectedId).toBe('c-alpha')
    expect(JSON.stringify(useToastStore().$state)).toContain('no longer on the cluster list')
    expect(router.currentRoute.value.name).toBe('settings-cluster')
    expect(document.querySelector('.bell-row')).toBeNull()
  })

  it('does not mark an already read row read again', async () => {
    await openBell(notice('c-beta', DUE, true))
    row().click()
    await flushPromises()
    expect(sdk.markReadApiV1NotificationsNotificationIdReadPatch).not.toHaveBeenCalled()
  })
})

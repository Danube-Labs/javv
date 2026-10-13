/**
 * Bell feed (M9f slice 3, FR-16/NFR-9): polls `GET /api/v1/notifications` — no broker, the
 * badge count is the SERVER's unread count, never a client tally. Degraded rule (SCREENS §14):
 * a failed poll PAUSES the badge (no stale count) and the drawer says so. Cadence matches the
 * health poll's 30s constant.
 */
import { computed, ref } from 'vue'

import { client } from '@/api/client'
import {
  deleteNotificationApiV1NotificationsNotificationIdDelete,
  listNotificationsApiV1NotificationsGet,
  markReadApiV1NotificationsNotificationIdReadPatch,
} from '@/api/generated'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

export interface NotificationItem {
  notification_id: string
  type: string // report_ready | sla_breach | assignment | cluster_retiring
  ref: string | null
  cluster_id: string | null
  /** the cluster's name when the feed was read, its id if never named; null with no cluster */
  cluster_name?: string | null
  created_at: string
  read: boolean
}

const POLL_MS = 30_000 // same cadence as stores/health.ts

const ECHO_COPY: Record<string, string> = {
  report_ready: 'Export ready',
  sla_breach: 'SLA breached on a finding assigned to you',
  assignment: 'A finding was assigned to you',
}

export function useNotifications() {
  const items = ref<NotificationItem[]>([])
  const unread = ref(0)
  const failed = ref(false)
  const loaded = ref(false)
  let handle: ReturnType<typeof setInterval> | 0 = 0

  async function refresh() {
    const response = await listNotificationsApiV1NotificationsGet({ client })
    if (response.response?.ok && response.data) {
      const body = response.data as { unread: number; items: NotificationItem[] }
      // the toast ECHO (operator 2026-07-17): a notification landing while the user watches
      // gets an immediate ephemeral ping; the bell entry stays the durable record. Only for
      // arrivals AFTER the first load — never a replay of the backlog.
      if (loaded.value) {
        const known = new Set(items.value.map((i) => i.notification_id))
        const fresh = (body.items ?? []).filter((i) => !i.read && !known.has(i.notification_id))
        if (fresh.length === 1) {
          useToastStore().info(`${ECHO_COPY[fresh[0]!.type] ?? 'New notification'}. Open the bell.`)
        } else if (fresh.length > 1) {
          useToastStore().info(`${fresh.length} new notifications. Open the bell.`)
        }
      }
      unread.value = body.unread
      items.value = body.items ?? []
      failed.value = false
    } else {
      failed.value = true // badge pauses — never show a stale count
      logger.warn('notifications_poll_failed', { status: response.response?.status })
    }
    loaded.value = true
  }

  function startPolling() {
    if (handle) return
    void refresh()
    handle = setInterval(() => void refresh(), POLL_MS)
  }

  function stopPolling() {
    if (handle) clearInterval(handle)
    handle = 0
  }

  async function markRead(notificationId: string) {
    const response = await markReadApiV1NotificationsNotificationIdReadPatch({
      client,
      path: { notification_id: notificationId },
    })
    if (response.response?.ok) {
      const hit = items.value.find((i) => i.notification_id === notificationId)
      if (hit && !hit.read) {
        hit.read = true
        unread.value = Math.max(0, unread.value - 1)
      }
    } else if (response.response?.status === 404) {
      // already gone server-side (TTL sweep raced the feed) — drop the stale row
      const hit = items.value.find((i) => i.notification_id === notificationId)
      if (hit && !hit.read) unread.value = Math.max(0, unread.value - 1)
      items.value = items.value.filter((i) => i.notification_id !== notificationId)
      logger.info('notification_already_gone', { notification_id: notificationId })
    } else {
      logger.warn('notification_mark_read_failed', { status: response.response?.status })
    }
  }

  async function dismiss(notificationId: string) {
    const response = await deleteNotificationApiV1NotificationsNotificationIdDelete({
      client,
      path: { notification_id: notificationId },
    })
    if (response.response?.ok || response.response?.status === 404) {
      // 404 = already gone server-side (TTL sweep raced the feed) — same outcome for the UI
      const hit = items.value.find((i) => i.notification_id === notificationId)
      if (hit && !hit.read) unread.value = Math.max(0, unread.value - 1)
      items.value = items.value.filter((i) => i.notification_id !== notificationId)
    } else {
      logger.warn('notification_dismiss_failed', { status: response.response?.status })
    }
  }

  /** loops the per-id routes — the feed is ≤50 docs, no bulk endpoint needed at this size;
   * both end on a refresh so the badge is the SERVER's count again, never a client tally */
  async function markAllRead() {
    await Promise.all(items.value.filter((i) => !i.read).map((i) => markRead(i.notification_id)))
    await refresh()
  }

  async function clearAll() {
    await Promise.all(items.value.map((i) => dismiss(i.notification_id)))
    await refresh()
  }

  const badge = computed(() => (failed.value ? null : unread.value))

  return {
    items,
    unread,
    failed,
    loaded,
    badge,
    refresh,
    startPolling,
    stopPolling,
    markRead,
    dismiss,
    markAllRead,
    clearAll,
  }
}

<script setup lang="ts">
/**
 * Notification bell (M9f slice 3, FR-16 / SCREENS §14 — Nuxt inbox grammar on JAVV tokens):
 * count chip with a card-colored ring on the trigger (the UChip convention), drawer =
 * SlideoverShell (banked by the docked-triage ruling for exactly this), rows = icon tile ·
 * title + muted description · timestamp at the trailing edge · unread dot.
 * Categories: ready-export (resolves the signed download on click; expired flips the item —
 * never a dead link) · sla_breach · assignment (writers land with their owning bolts) ·
 * cluster_retiring (issue 765: a cluster entered its warning window; opens Settings › Cluster
 * for it, where its window and Bring back are).
 * Degraded rule: the badge PAUSES — no stale count.
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { client } from '@/api/client'
import { getReportApiV1ReportsReportIdGet } from '@/api/generated'
import AppIcon from '@/components/ui/AppIcon.vue'
import SlideoverShell from '@/components/ui/SlideoverShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useNotifications, type NotificationItem } from '@/composables/useNotifications'
import { fmtAt } from '@/findings/format'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'

const toast = useToastStore()
const router = useRouter()
const clusterStore = useClusterStore()
const bell = useNotifications()
const open = ref(false)
const expired = ref(new Set<string>())

onMounted(() => bell.startPolling())
onUnmounted(() => bell.stopPolling())

type Meta = { icon: 'download' | 'clock' | 'shield' | 'alert'; label: string; desc: string }

const COPY: Record<string, Meta> = {
  report_ready: {
    icon: 'download',
    label: 'Export ready',
    desc: 'Your scheduled export finished. Open to download.',
  },
  sla_breach: {
    icon: 'clock',
    label: 'SLA breached',
    desc: 'A finding assigned to you ran past its SLA window.',
  },
  assignment: {
    icon: 'shield',
    label: 'Assigned to you',
    desc: 'A finding was assigned to you for triage.',
  },
}

/** The retirement date in the notification (`ref` = `retires_at`), as "14 Oct". The sweep
 * retires on its first run from that moment, so the row says "due", not "will be retired on". */
function onDay(iso: string | null): string | null {
  const at = iso ? new Date(iso) : null
  return at && !Number.isNaN(at.getTime())
    ? at.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
    : null
}

function retiringDesc(name: string, iso: string | null): string {
  const day = onDay(iso)
  if (!day) return `${name} is due to be retired soon unless a scan arrives.`
  // a cluster held past its date (the sweep retires nothing while no cluster scans)
  return new Date(iso as string).getTime() < Date.now()
    ? `${name} was due to be retired on ${day} and will be retired unless a scan arrives.`
    : `${name} is due to be retired on ${day} unless a scan arrives.`
}

function meta(item: NotificationItem): Meta {
  if (item.type === 'cluster_retiring') {
    const id = item.cluster_id ?? ''
    const listed = clusterStore.clusters.find((c) => c.cluster_id === id)
    // a retired cluster keeps its notice (operator ruling 2026-10-08); it is off the list, so the
    // row says what happened rather than what was due
    const retired = clusterStore.loaded && !listed
    // off the list once retired: the feed carries the name for that (issue 787)
    const name = listed?.cluster_name ?? item.cluster_name ?? id
    // the title names the event, like every other row; ruled on built A/B specimens 2026-10-07
    return {
      icon: 'alert',
      label: 'Cluster retiring',
      desc: retired ? `${name} has been retired.` : retiringDesc(name, item.ref),
    }
  }
  return COPY[item.type] ?? { icon: 'shield', label: item.type, desc: '' }
}

/** cluster_retiring: open that cluster's Settings › Cluster, if it is still listed. The list
 * is re-read first: the sweep may have retired it since the last poll. */
async function openCluster(item: NotificationItem) {
  if (!item.read) void bell.markRead(item.notification_id)
  open.value = false
  await clusterStore.refresh()
  const id = item.cluster_id
  if (!id || !clusterStore.clusters.some((c) => c.cluster_id === id)) {
    toast.info('That cluster is no longer on the cluster list. Retired clusters are in Settings › Cluster.')
  } else {
    clusterStore.select(id)
  }
  void router.push({ name: 'settings-cluster' })
}

/** ready-export: resolve the signed link on click — the report GET carries the token; an
 * expired/failed report flips the item instead of opening a dead tab (C-2/410 rule). */
async function openExport(item: NotificationItem) {
  if (!item.ref) return
  const response = await getReportApiV1ReportsReportIdGet({
    client,
    path: { report_id: item.ref },
  })
  const body = (response.data ?? null) as { status?: string; download_token?: string } | null
  if (response.response?.ok && body?.download_token) {
    window.open(
      `/api/v1/reports/${item.ref}/download?token=${encodeURIComponent(body.download_token)}`,
      '_blank',
    )
    void bell.markRead(item.notification_id)
  } else {
    expired.value.add(item.notification_id)
    expired.value = new Set(expired.value)
    toast.info('That export expired. Re-run it from the Findings screen.')
    logger.info('notification_export_expired', { report_id: item.ref })
    void bell.markRead(item.notification_id)
  }
}

function onRowClick(item: NotificationItem) {
  if (item.type === 'report_ready' && !expired.value.has(item.notification_id)) {
    void openExport(item)
  } else if (item.type === 'cluster_retiring') {
    void openCluster(item)
  } else if (!item.read) {
    void bell.markRead(item.notification_id)
  }
}
</script>

<template>
  <div class="bell-wrap">
    <button
      type="button"
      class="bell-btn"
      :aria-label="`Notifications${bell.badge.value ? ` (${bell.badge.value} unread)` : ''}`"
      @click="open = !open"
    >
      <AppIcon name="bell" :size="17" />
      <span v-if="bell.badge.value" class="bell-badge">{{ bell.badge.value > 99 ? '99+' : bell.badge.value }}</span>
    </button>

    <SlideoverShell v-if="open" title="Notifications" subtitle="polled · newest first" @close="open = false">
      <div class="bell-list">
        <div v-if="bell.items.value.length" class="bell-actions">
          <UiButton v-if="bell.unread.value" variant="mini" @click="bell.markAllRead()">
            <AppIcon name="check" :size="12" />Mark all read
          </UiButton>
          <UiButton variant="mini" @click="bell.clearAll()">× Clear all</UiButton>
        </div>
        <p v-if="bell.failed.value" class="bell-degraded" role="alert">
          Notifications unavailable. The badge is paused, nothing here is stale.
        </p>
        <p v-else-if="bell.loaded.value && bell.items.value.length === 0" class="bell-empty" role="status">
          Nothing yet. SLA breaches, new assignments, ready exports and clusters about to be retired land here.
        </p>
        <div
          v-for="item in bell.items.value"
          :key="item.notification_id"
          role="button"
          tabindex="0"
          class="bell-row"
          :class="{ unread: !item.read }"
          @click="onRowClick(item)"
          @keydown.enter="onRowClick(item)"
        >
          <span class="bell-tile"><AppIcon :name="meta(item).icon" :size="15" /></span>
          <span class="bell-body">
            <span class="bell-title-row">
              <span class="bell-label">{{ meta(item).label }}</span>
              <span class="bell-when">{{ fmtAt(item.created_at) }}</span>
            </span>
            <span class="bell-desc">
              <template v-if="expired.has(item.notification_id)">Expired. Re-run the export from Findings.</template>
              <template v-else>{{ meta(item).desc }}</template>
            </span>
          </span>
          <AppIcon
            v-if="(item.type === 'report_ready' && !expired.has(item.notification_id)) || item.type === 'cluster_retiring'"
            class="bell-go"
            name="chevron"
            :size="11"
          />
          <span v-if="!item.read" class="bell-dot" aria-label="unread" />
          <button
            type="button"
            class="bell-x"
            :aria-label="`Dismiss ${meta(item).label}`"
            @click.stop="bell.dismiss(item.notification_id)"
          >
            ×
          </button>
        </div>
      </div>
    </SlideoverShell>
  </div>
</template>

<style scoped>
.bell-wrap {
  position: relative;
  display: flex;
}
.bell-btn {
  position: relative;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--card);
  color: var(--soft);
  cursor: default;
}
.bell-btn:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
  color: var(--ink);
}
.bell-btn:active {
  background: var(--line2);
}
/* the UChip convention: count pill on the trigger's corner, ringed in the surface color */
.bell-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: 9px;
  background: var(--coral);
  color: var(--kev-fg);
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  display: grid;
  place-items: center;
  box-shadow: 0 0 0 2px var(--card);
}
.bell-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px;
}
.bell-degraded {
  margin: 8px 6px;
  color: var(--health-down-fg);
  font-size: var(--text-sm);
}
.bell-empty {
  margin: 24px 12px;
  text-align: center;
  color: var(--soft);
  font-size: var(--text-body);
}
.bell-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  background: transparent;
  padding: 10px;
  text-align: left;
  font-family: var(--font-ui);
  cursor: default;
}
.bell-row:hover {
  background: var(--row-hover);
  border-color: var(--line2);
}
.bell-row:active {
  background: var(--line2);
}
.bell-tile {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--r-sm);
  background: var(--panel);
  border: 1px solid var(--line2);
  color: var(--soft);
}
.bell-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.bell-title-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}
.bell-label {
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--soft);
}
.bell-row.unread .bell-label {
  color: var(--ink);
  font-weight: 600;
}
.bell-when {
  flex: none;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
.bell-desc {
  font-size: var(--text-sm);
  color: var(--soft);
}
.bell-go {
  flex: none;
  align-self: center;
  color: var(--dash-muted);
}
.bell-row:hover .bell-go {
  color: var(--coral-text);
}
.bell-dot {
  flex: none;
  align-self: center;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--coral);
}
.bell-actions {
  display: flex;
  justify-content: flex-end;
  gap: 14px;
  padding: 4px 8px 6px;
  border-bottom: 1px solid var(--line2);
  margin-bottom: 4px;
}
.bell-x {
  flex: none;
  align-self: center;
  display: grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border: 0;
  border-radius: var(--r-chip);
  background: transparent;
  color: var(--soft);
  font-size: var(--text-card-title);
  line-height: 1;
  cursor: default;
}
.bell-x:hover {
  background: var(--fpill-x-hover-bg);
  color: var(--coral-text);
}
</style>

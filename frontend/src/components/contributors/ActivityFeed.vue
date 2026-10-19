<script setup lang="ts">
/**
 * Recent-activity feed (M9d slice 3; prototype `.feed`, flat by ruling — an activity feed is
 * reverse-chronological, not a process): the newest journaled events, straight from the M8c
 * audit read with its read-time decoration (CVE + severity ride along for free). Capped at a
 * page — the full stream is the Audit log screen's job, linked below. Click-through only where
 * the finding decoration survives (A-5), same contract as the audit table.
 */
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { closeUnpaged } from '@/api/cursors'
import { readAuditLogApiV1AuditGet } from '@/api/generated'
import type { ReadAuditLogApiV1AuditGetData } from '@/api/generated'
import { feedDetail } from '@/audit/auditDetail'
import ActionTag from '@/components/chips/ActionTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import ContributorIdentity from '@/components/contributors/ContributorIdentity.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import type { AuditEvent } from '@/stores/audit'
import { lastDataAt } from '@/system/freshness'

// a display cap, not a setting: the feed shows one glance's worth — "view all" is the audit screen
const FEED_SIZE = 8

const props = defineProps<{
  /** the screen's global query (cluster_id + as_of) — the feed rewinds with the app */
  query: Record<string, unknown> | null
}>()
const router = useRouter()

const rows = ref<AuditEvent[]>([])
const failed = ref(false)
const settled = ref(false)

watch(
  () => props.query,
  async (q, old) => {
    if (!q) return
    if (old && old.cluster_id !== q.cluster_id) {
      settled.value = false
      rows.value = []
    }
    const response = await readAuditLogApiV1AuditGet({
      query: { ...q, size: FEED_SIZE } as ReadAuditLogApiV1AuditGetData['query'],
    })
    closeUnpaged(response.data?.next_cursor, true) // the feed shows one page and never pages
    failed.value = !response.response?.ok || !response.data
    if (failed.value) {
      logger.warn('contrib_feed_failed', { status: response.response?.status })
      rows.value = []
    } else {
      rows.value = (response.data as unknown as { data: AuditEvent[] }).data ?? []
    }
    settled.value = true
  },
  { immediate: true, deep: true },
)

function openFinding(row: AuditEvent) {
  const f = row.finding
  if (!f) return
  logger.debug('contrib_feed_clicked', { finding_key: row.entity_id })
  void router.push({
    name: 'finding',
    params: { cveId: f.cve_id },
    query: {
      digest: String(f.image_digest ?? ''),
      scanner: f.scanner ?? '',
      pkg: f.package_name ?? '',
    },
  })
}
</script>

<template>
  <div v-if="!settled" class="feed-skel" aria-busy="true" aria-label="Loading recent activity">
    <UiSkeleton v-for="i in 4" :key="i" :height="34" radius="sm" />
  </div>
  <p v-else-if="failed" class="load-error" role="alert">
    Recent activity unavailable. Check the backend connection.
  </p>
  <p v-else-if="rows.length === 0" class="feed-empty" role="status">
    No journaled activity yet. Triage actions land here as they happen.
  </p>
  <div v-else class="feed">
    <component
      :is="row.finding ? 'button' : 'div'"
      v-for="row in rows"
      :key="row.event_id"
      class="feed-item"
      :class="{ 'feed-linked': row.finding }"
      v-on="row.finding ? { click: () => openFinding(row) } : {}"
    >
      <ContributorIdentity :actor="row.actor" :size="30" />
      <div class="feed-body">
        <div class="feed-line">
          <ActionTag :action="row.action" />
          <span v-if="row.finding" class="mono-cell sm feed-cve">{{ row.finding.cve_id }}</span>
          <SevChip
            v-if="row.finding?.severity_canonical"
            :level="row.finding.severity_canonical"
          />
          <span v-else-if="row.decision" class="mono-cell sm feed-cve"
            >{{ row.decision.cve_id }} · decision</span
          >
        </div>
        <div v-if="feedDetail(row)" class="feed-note">{{ feedDetail(row) }}</div>
      </div>
      <span class="feed-when mono-cell" :title="row['@timestamp']">{{
        lastDataAt(row['@timestamp'])
      }}</span>
    </component>
    <router-link class="feed-all" :to="{ name: 'audit' }"
      >View all in Audit log →</router-link
    >
  </div>
</template>

<style scoped>
/* prototype .feed family on tokens; items are buttons only when click-through is meaningful */
.feed {
  display: flex;
  flex-direction: column;
}
.feed-item {
  display: flex;
  gap: 11px;
  align-items: flex-start;
  padding: 11px 6px;
  border: none;
  border-bottom: 1px solid var(--line2);
  background: none;
  text-align: left;
  width: 100%;
  font: inherit;
  color: inherit;
}
.feed-linked {
  transition: background var(--dur-quick);
}
.feed-linked:hover {
  background: var(--control-hover-bg);
  border-radius: var(--r-sm);
}
.feed-linked:active {
  background: var(--control-active-bg);
}
.feed-linked:focus-visible {
  outline: var(--focus-ring);
  outline-offset: -2px;
}
.feed-body {
  flex: 1;
  min-width: 0;
}
.feed-line {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.feed-cve {
  color: var(--ink);
}
.feed-note {
  font-size: var(--text-sm);
  color: var(--soft);
  margin-top: 3px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.feed-when {
  font-size: var(--text-control);
  color: var(--muted);
  flex: none;
  white-space: nowrap;
  padding-top: 2px;
}
.feed-all {
  margin-top: 10px;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--teal);
  text-decoration: none;
  align-self: flex-start;
  padding: 4px 6px;
  border-radius: var(--r-sm);
  transition: background var(--dur-quick);
}
.feed-all:hover {
  background: var(--control-hover-bg);
  text-decoration: underline;
}
.feed-all:focus-visible {
  outline: var(--focus-ring);
}
.feed-empty {
  margin: 0;
  padding: var(--space-4) 0;
  color: var(--soft);
  font-size: var(--text-body);
}
.load-error {
  margin: 0;
}
.feed-skel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 8px 0;
}
</style>

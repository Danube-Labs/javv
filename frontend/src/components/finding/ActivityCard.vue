<script setup lang="ts">
/**
 * Per-finding activity list (issue 434 refresh): the audit-trail rows for THIS finding_key —
 * capped at a glance, the full trail lives on the Audit screen. DetailCard chrome; the body
 * stays a list, not a table (two columns of prose is not tabular data).
 */
import { bulkChange } from '@/audit/bulkAudit'
import ActionTag from '@/components/chips/ActionTag.vue'
import StateTag from '@/components/chips/StateTag.vue'
import DetailCard from '@/components/finding/DetailCard.vue'
import GridPager from '@/components/findings/GridPager.vue'
import { usePagedSlice } from '@/composables/usePagedSlice'
import { fmtAt } from '@/findings/format'

export interface ActivityRow {
  event_id: string
  action: string
  actor: string
  field?: string
  old_value?: string | null
  new_value?: string | null
  /** a bulk change keeps what it set here, in `patch` */
  new_value_json?: Record<string, unknown> | null
  '@timestamp': string
}

const props = defineProps<{
  activity: ActivityRow[]
  /** the activity read was refused: say so, never "none" (issue 833, F2) */
  failed?: boolean
}>()

/* display slices through the shared GridPager — the FULL trail still lives on Audit */
const { page, size, shown, hasNext, setSize } = usePagedSlice(() => props.activity)
</script>

<template>
  <DetailCard title="Activity on this finding" sub="the audit trail: every triage action, who &amp; when" flush dark-head>
    <div class="act-body">
    <p v-if="activity.length === 0" class="empty-row">{{ failed ? 'Could not be loaded.' : 'No triage actions yet.' }}</p>
    <ul v-else class="act-list">
      <li v-for="a in shown" :key="a.event_id" class="act-row">
        <span class="act-when mono-cell">{{ fmtAt(a['@timestamp']) }}</span>
        <span class="act-what">
          <b>{{ a.actor }}</b> · <ActionTag :action="a.action" />
          <!-- a single state change adds nothing: the action pill already names the state it set -->
          <template v-if="bulkChange(a)">
            <template v-if="bulkChange(a)!.state"> · <StateTag :state="bulkChange(a)!.state!" /></template>
            <span v-if="bulkChange(a)!.assignee" class="act-part">
              · assignee: <span class="mono-cell sm">{{ bulkChange(a)!.assignee }}</span>
            </span>
            <span v-if="bulkChange(a)!.notes" class="act-part">
              · notes: <span class="mono-cell sm">{{ bulkChange(a)!.notes }}</span>
            </span>
          </template>
          <template v-else-if="a.new_value && a.field !== 'state'">
            · {{ a.field }}: <span class="mono-cell sm">{{ a.new_value }}</span>
          </template>
        </span>
      </li>
    </ul>
    <p v-if="activity.length >= 50" class="cap-note">Latest 50 actions. The full trail lives on the Audit screen.</p>
    </div>
    <GridPager
      :total="activity.length"
      :page="page"
      :size="size"
      :shown="shown.length"
      :has-prev="page > 0"
      :has-next="hasNext"
      class="act-pager"
      @prev="page -= 1"
      @next="page += 1"
      @update:size="setSize"
    />
  </DetailCard>
</template>

<style scoped>
.mono-cell {
  font-family: var(--font-mono);
}
.sm {
  font-size: var(--text-sm);
}
.act-body {
  padding: 14px 16px;
}
.cap-note {
  margin: 10px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.act-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.act-row {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: var(--text-body);
}
.act-when {
  flex: none;
  font-size: var(--text-sm);
  color: var(--soft);
  min-width: 92px;
}
.act-what {
  display: inline-flex;
  flex-wrap: wrap; /* a bulk change has more parts than one line holds: wrap whole parts */
  align-items: center;
  gap: 2px 6px;
  min-width: 0;
  color: var(--ink);
}
.act-part {
  min-width: 0;
}
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 28px 12px;
}
</style>

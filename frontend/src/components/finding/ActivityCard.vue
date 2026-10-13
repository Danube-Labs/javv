<script setup lang="ts">
/**
 * Per-finding activity list (issue 434 refresh): the audit-trail rows for THIS finding_key —
 * capped at a glance, the full trail lives on the Audit screen. DetailCard chrome; the body
 * stays a list, not a table (two columns of prose is not tabular data).
 */
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
          <b>{{ a.actor }}</b> · {{ a.action }}
          <template v-if="a.field === 'state' && a.new_value">
            · <StateTag :state="a.new_value" />
          </template>
          <template v-else-if="a.new_value">
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
  align-items: center;
  gap: 6px;
  color: var(--ink);
}
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 28px 12px;
}
</style>

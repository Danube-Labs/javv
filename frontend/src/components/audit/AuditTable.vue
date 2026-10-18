<script setup lang="ts">
/**
 * The audit table (prototype screens-audit.jsx `AuditLog` table, ported per DESIGN.md §8 —
 * operator ruling 2026-07-12 superseding the timeline note: prototype grammar, shared skin):
 * When · User · Action · Detail · Target on `tbl tbl-dense tbl-hover` (Detail is a `fit`
 * column so the layout slack pools in Target — the identity column was getting squeezed to
 * a sliver while Detail hogged the row; operator ruling 2026-07-18). Rows come in the
 * server's `(@timestamp, event_id)` walk and are re-read causally per page (`causalOrder`,
 * D38/H8): same-field edits display by `revision` (the `rev` badge). The Target column reads
 * the row's read-time decoration — CVE + severity + image for findings (the operator's "what
 * changed, on what"), CVE + type for decisions — and degrades to the bare entity id once the
 * doc ages out of the store (history outlives current state). Click-through only where
 * `entity_type === 'finding'` (A-5); the Task column is dropped (V4-DELTA-1, Jira = v1.1).
 */
import Column from 'primevue/column'
import DataTable from 'primevue/datatable'
import { computed } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import { actionLabel } from '@/audit/actionLabels'
import { bulkJson } from '@/audit/bulkAudit'
import { causalOrder } from '@/audit/causalOrder'
import ActionTag from '@/components/chips/ActionTag.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import ValueActions from '@/components/filters/ValueActions.vue'
import RowLink from '@/components/ui/RowLink.vue'
import { activeMode, type Selections } from '@/filters/fields.config'
import { lastDataAt } from '@/system/freshness'
import type { AuditEvent } from '@/stores/audit'
import type { FilterMode, Modes } from '@/stores/filters'

const props = defineProps<{
  rows: AuditEvent[]
  loading?: boolean
  /** the read was refused: the table has no answer, so it must not say "no activity" */
  failed?: boolean
  filtered?: boolean
  /** active selections + modes, so a cell action shows which side it already sits on */
  selections?: Selections
  modes?: Modes
  /** where a finding row leads: its CVE renders as a real link, so the keyboard can open it */
  rowTo?: (row: AuditEvent) => RouteLocationRaw | null
}>()
const emit = defineEmits<{
  rowClick: [row: AuditEvent]
  /** a cell's value action (issue 349 §2): filter TO / OUT of this exact value */
  pickValue: [fieldKey: string, value: string, mode: FilterMode]
}>()

/** `actor` and `action` are the AUDIT_FIELDS keys; both carry an `exclude_*` twin server-side. */
const cellActive = (fieldKey: string, value: string): FilterMode | null =>
  activeMode(fieldKey, value, props.selections, props.modes)

const ordered = computed(() => causalOrder(props.rows))

const clickable = (e: AuditEvent) => e.entity_type === 'finding' && !!e.finding_key && !!e.finding

/** mono identity fallback when a row has no decoration — Target owns the layout slack, so
 * only truly long ids (raw finding keys) get clipped; store/job ids show whole */
const shortId = (id: string) => (id.length > 72 ? `${id.slice(0, 68)}…` : id)

const shortImage = (e: AuditEvent) => (e.finding?.image_repo ?? '').split('/').pop() ?? ''

/** one-line what-changed; empty when the tag + target already say it all (auth events) */
function detail(e: AuditEvent): string {
  const bulk = bulkJson(e)
  if (bulk) {
    const patch = Object.entries(bulk.patch ?? {})
      .map(([k, v]) => `${k} → ${String(v)}`)
      .join(' · ')
    return `${patch}: ${bulk.result_count ?? '?'} findings (frozen set)`
  }
  if (e.field == null) return ''
  if (e.old_value == null && e.new_value == null) return ''
  if (e.old_value == null) return `${e.field}: ${e.new_value}`
  if (e.new_value == null) return `${e.field}: ${e.old_value} cleared`
  return `${e.field}: ${e.old_value} → ${e.new_value}`
}

function onRowClick(row: AuditEvent) {
  if (clickable(row)) emit('rowClick', row)
}
</script>

<template>
  <div class="tbl-wrap">
    <DataTable
      :value="ordered"
      lazy
      :loading="props.loading"
      data-key="event_id"
      :pt="{ table: { class: 'tbl tbl-dense tbl-hover' } }"
      @row-click="(e) => onRowClick(e.data as AuditEvent)"
    >
      <Column header="When" class="fit">
        <template #body="{ data }">
          <span class="mono-cell sm nowrap" :title="data['@timestamp']">{{ lastDataAt(data['@timestamp']) }}</span>
        </template>
      </Column>
      <Column header="User" class="fit">
        <template #body="{ data }">
          <span class="cell-actionable">
            <span class="actor-cell">{{ data.actor }}</span>
            <ValueActions
              v-if="data.actor"
              class="val-act-reveal"
              field="User"
              :value="data.actor"
              :active="cellActive('actor', data.actor)"
              @pick="(m) => emit('pickValue', 'actor', data.actor, m)"
            />
          </span>
        </template>
      </Column>
      <Column header="Action" class="fit">
        <template #body="{ data }">
          <span class="cell-actionable">
            <ActionTag :action="data.action" />
            <ValueActions
              v-if="data.action"
              class="val-act-reveal"
              field="Action"
              :value="data.action"
              :shown="actionLabel(data.action)"
              :active="cellActive('action', data.action)"
              @pick="(m) => emit('pickValue', 'action', data.action, m)"
            />
          </span>
        </template>
      </Column>
      <Column header="Detail" class="fit">
        <template #body="{ data }">
          <span class="detail-cell">
            <span class="wrap-cell soft" :title="detail(data)">{{ detail(data) || '-' }}</span>
            <span
              v-if="data.revision != null && data.field != null"
              class="rev-badge"
              title="Revision: same-field edits replay in this order, not by timestamp, because the revision is the finding's version when the edit landed, so a retried or near-simultaneous edit can't jump ahead."
              >rev {{ data.revision }}</span
            >
          </span>
        </template>
      </Column>
      <Column header="Target">
        <template #body="{ data }">
          <span v-if="data.finding" class="audit-target">
            <RowLink v-if="clickable(data) && props.rowTo?.(data)" :to="props.rowTo(data)!" @open="onRowClick(data)">
              <span class="mono-cell strong sm nowrap cve-link">{{ data.finding.cve_id }}</span>
            </RowLink>
            <span v-else class="mono-cell strong sm nowrap" :class="{ 'cve-link': clickable(data) }">{{ data.finding.cve_id }}</span>
            <SevChip v-if="data.finding.severity_canonical" :level="data.finding.severity_canonical" :dot="true" />
            <span class="mono-cell sm img-cell" :title="data.finding.image_repo ?? ''">{{ shortImage(data) }}</span>
            <ScannerTag v-if="data.finding.scanner" :name="data.finding.scanner" />
          </span>
          <span v-else-if="data.decision" class="audit-target">
            <span class="mono-cell strong sm nowrap">{{ data.decision.cve_id }}</span>
            <span class="target-kind">{{ data.decision.type === 'risk_accepted' ? 'risk accept' : (data.decision.type ?? 'decision') }}</span>
            <span class="target-kind">{{ data.decision.apply_both_scanners ? 'both scanners' : (data.decision.scanner ?? '') }}</span>
          </span>
          <span v-else class="audit-target">
            <span class="mono-cell sm" :title="data.entity_id">{{ shortId(data.entity_id) }}</span>
            <span class="target-kind">{{ data.entity_type }}</span>
          </span>
        </template>
      </Column>
      <template #empty>
        <!-- while a fresh lens loads (rows just cleared), say loading — "no activity" would lie -->
        <div class="empty-row">
          {{ props.loading ? 'Loading events…'
            : props.failed ? 'Events could not be loaded.'
            : filtered ? 'No events match these filters.'
            : 'No journaled activity for this cluster yet. Triage actions, decisions and config edits will land here.' }}
        </div>
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
/* the table skin (.tbl-wrap / .tbl family / empty-row) lives in base.css */
:deep(.actor-cell) {
  font-weight: 600;
  font-size: var(--text-sm);
  white-space: nowrap;
}
:deep(.audit-target) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
:deep(.target-kind) {
  font-size: var(--text-sm);
  color: var(--soft);
}
:deep(.detail-cell) {
  display: flex;
  align-items: center;
  gap: 8px;
}
:deep(.wrap-cell) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 46ch;
}
:deep(.soft) {
  color: var(--soft);
}
:deep(.rev-badge) {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
  border: 1px solid var(--line);
  border-radius: 4px;
  padding: 0 5px;
  white-space: nowrap;
}
/* the affordance carrier, same grammar as the findings grid: the identifier lights up on a
   live row (only decorated finding rows navigate) */
:deep(.cve-link) {
  transition: color 0.12s ease-out;
}
:deep(.tbl-hover tbody tr:hover .cve-link) {
  color: var(--coral-text);
}
</style>

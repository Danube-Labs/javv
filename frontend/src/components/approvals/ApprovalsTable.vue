<script setup lang="ts">
/**
 * The Approvals queue table: one row per standing risk-acceptance, with the cell filter actions
 * and the in-row Edit and two-click Revoke. The view owns the fetch, the filters and the revoke
 * request; this table owns only its rows.
 */
import { ref } from 'vue'

import {
  expiryStatus,
  findingsRoute,
  scannerLabel,
  scopeLabel,
  type ApprovalRow,
} from '@/approvals/viewModel'
import ExpiryChip from '@/components/chips/ExpiryChip.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import ValueActions from '@/components/filters/ValueActions.vue'
import RowLink from '@/components/ui/RowLink.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { activeMode, type Selections } from '@/filters/fields.config'
import type { FilterMode, Modes } from '@/stores/filters'
import { lastDataAt } from '@/system/freshness'

const props = defineProps<{
  rows: readonly ApprovalRow[]
  /** the display clock (D28) the countdowns and the status measure from */
  nowMs: number
  selections: Selections
  modes: Modes
  /** a revoke or an edit is in flight: the row actions wait */
  busy: boolean
}>()

const emit = defineEmits<{
  open: [row: ApprovalRow]
  pick: [fieldKey: string, value: string, mode: FilterMode]
  edit: [row: ApprovalRow]
  revoke: [row: ApprovalRow]
}>()

/** The scanner column's own value — the `both | trivy | grype` the filter field takes, not
 * the tag's display text (issue 349 §2). */
const scannerValue = (row: ApprovalRow) =>
  row.apply_both_scanners || !row.scanner ? 'both' : row.scanner

/** The mode this exact value is already filtered under, so the active side reads as pressed. */
const cellActive = (fieldKey: string, value: string): FilterMode | null =>
  activeMode(fieldKey, value, props.selections, props.modes)

/* two-click revoke: the first click arms the row, the second asks the view to revoke */
const armed = ref<string | null>(null)
function revoke(row: ApprovalRow) {
  if (armed.value !== row.decision_id) {
    armed.value = row.decision_id
    return
  }
  armed.value = null
  emit('revoke', row)
}
</script>

<template>
  <div class="tbl-scroll-pin">
    <table class="tbl tbl-hover">
      <thead>
        <tr>
          <th>CVE</th>
          <th>Scope</th>
          <th>Scanner</th>
          <th>Justification</th>
          <th>Approver</th>
          <th class="fit">Expires</th>
          <th class="fit">Status</th>
          <th class="fit">Created</th>
          <th class="fit"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.decision_id" @click="emit('open', row)">
          <td>
            <RowLink :to="findingsRoute(row)" @open="emit('open', row)"><span class="mono-cell strong nowrap cve-link">{{ row.cve_id }}</span></RowLink>
          </td>
          <td>
            <span class="scope-cell" :class="{ 'scope-wide': scopeLabel(row.scope) === 'cluster-wide' }">
              {{ scopeLabel(row.scope) }}
            </span>
          </td>
          <td>
            <span class="cell-actionable">
              <ScannerTag v-if="!row.apply_both_scanners && row.scanner" :name="row.scanner" />
              <span v-else class="both-tag">{{ scannerLabel(row) }}</span>
              <ValueActions
                class="val-act-reveal"
                field="Scanner"
                :value="scannerValue(row)"
                :active="cellActive('scanner', scannerValue(row))"
                @pick="(m) => emit('pick', 'scanner', scannerValue(row), m)"
              />
            </span>
          </td>
          <td class="just-cell" :title="row.justification">{{ row.justification }}</td>
          <td class="sm">
            <span class="cell-actionable">
              {{ row.created_by }}
              <ValueActions
                v-if="row.created_by"
                class="val-act-reveal"
                field="Approver"
                :value="row.created_by"
                :active="cellActive('approver', row.created_by)"
                @pick="(m) => emit('pick', 'approver', row.created_by, m)"
              />
            </span>
          </td>
          <td class="fit">
            <span class="mono-cell sm nowrap" :title="row.expiry ?? 'no expiry set'">
              <template v-if="row.expiry">{{ lastDataAt(row.expiry) }}</template><span v-else class="muted-dash">-</span>
            </span>
          </td>
          <td class="fit">
            <span class="cell-actionable">
              <ExpiryChip :expiry="row.expiry" :now-ms="nowMs" />
              <!-- status is DERIVED, so the action reuses the chip's own helper rather
                   than re-deriving it — the cell and the filter cannot disagree -->
              <ValueActions
                class="val-act-reveal"
                field="Status"
                :value="expiryStatus(row.expiry, nowMs)"
                :active="cellActive('status', expiryStatus(row.expiry, nowMs))"
                @pick="(m) => emit('pick', 'status', expiryStatus(row.expiry, nowMs), m)"
              />
            </span>
          </td>
          <td class="fit">
            <span class="mono-cell sm nowrap" :title="row.created_at">{{ lastDataAt(row.created_at) }}</span>
          </td>
          <td class="fit row-actions" @click.stop>
            <UiButton variant="mini" :disabled="busy" @click="emit('edit', row)">Edit</UiButton>
            <UiButton
              variant="mini"
              :class="{ 'revoke-armed': armed === row.decision_id }"
              :disabled="busy"
              @click="revoke(row)"
            >
              {{ armed === row.decision_id ? 'Confirm revoke' : 'Revoke' }}
            </UiButton>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.tbl th:first-child,
.tbl td:first-child {
  padding-left: 16px;
}
/* link affordance on the identifier, the findings-grid grammar */
:deep(.cve-link) {
  transition: color 0.12s ease-out;
}
.tbl-hover tbody tr:hover :deep(.cve-link) {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  :deep(.cve-link) {
    transition: none;
  }
}
.scope-cell {
  font-size: var(--text-sm);
}
.scope-wide {
  color: var(--soft);
  font-style: italic;
}
.both-tag {
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  color: var(--soft);
  background: var(--line2);
  padding: 2px 6px;
  border-radius: 4px;
}
.just-cell {
  max-width: 340px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-sm);
}
.row-actions {
  display: flex;
  gap: 6px;
  white-space: nowrap;
}
/* two-click revoke: the armed state speaks in the alarm register — hue in bg/border,
   prose stays ink (the style rules' same-hue rule, DESIGN.md §2) */
.row-actions :deep(.revoke-armed) {
  background: var(--sev-critical-bg);
  border-color: var(--sev-critical-solid);
  color: var(--ink);
}
</style>

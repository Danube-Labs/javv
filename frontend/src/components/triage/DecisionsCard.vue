<script setup lang="ts">
/**
 * "Decisions on this CVE" (issue 434 refresh) — scoped risk-accepts & not-affected calls.
 * Decisions are immutable (D40): revoked rows stay, struck through; expiry never edits.
 * The buttons follow the server's rule (issue 892): a risk-accept or an ignore rule is made and
 * revoked with can_accept_audit_final only, a not-affected decision is revoked with can_triage.
 * "New decision" makes a risk-accept, so it is the lead's. Kit skin + DetailCard chrome.
 */
import { computed } from 'vue'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import StateTag from '@/components/chips/StateTag.vue'
import DetailCard from '@/components/finding/DetailCard.vue'
import GridPager from '@/components/findings/GridPager.vue'
import { usePagedSlice } from '@/composables/usePagedSlice'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'

export interface DecisionRow {
  decision_id: string
  type: string
  scope?: { namespaces?: string[]; images?: string[] }
  apply_both_scanners?: boolean
  scanner?: string | null
  approver?: string | null
  created_by?: string | null
  expiry?: string | null
  revoked_at?: string | null
  [key: string]: unknown
}

const props = defineProps<{
  decisions: DecisionRow[]
  canAcceptFinal: boolean
  canTriage: boolean
  busy: boolean
  /** the decisions read was refused: say so, and offer no new decision against an unknown list
   * (issue 833, F2) */
  failed?: boolean
}>()
const emit = defineEmits<{ revoke: [id: string]; create: [] }>()

const rows = computed(() =>
  [...props.decisions].sort((a, b) => (a.revoked_at ? 1 : 0) - (b.revoked_at ? 1 : 0)),
)

/* display slices through the shared GridPager — decisions accrete forever (immutable +
 * revoked kept), so the card pages instead of walling */
const { page, size, shown, hasNext, setSize } = usePagedSlice(() => rows.value)

function canRevoke(d: DecisionRow): boolean {
  if (d.revoked_at) return false
  return props.canAcceptFinal || (props.canTriage && d.type === 'not_affected')
}

function scopeLabel(d: DecisionRow): string {
  const ns = d.scope?.namespaces ?? []
  const im = d.scope?.images ?? []
  if (ns.length === 0 && im.length === 0) return 'cluster-wide'
  return [...ns, ...im].join(', ')
}
</script>

<template>
  <DetailCard
    title="Decisions on this CVE"
    sub="scoped risk-accept / not-affected RULES (immutable; edits revoke + re-create). Plain state changes are triage actions, listed under Activity"
    flush
  >
    <template #action>
      <UiButton v-if="canAcceptFinal" :disabled="failed" @click="emit('create')">
        <AppIcon name="plus" :size="13" />New decision
      </UiButton>
    </template>
    <div class="tbl-wrap">
      <table class="tbl tbl-dense">
        <thead>
          <tr><th>Type</th><th>Scope</th><th>Scanners</th><th>By</th><th>Expiry</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-if="rows.length === 0">
            <td colspan="7" class="empty-row">{{ failed ? 'Could not be loaded.' : 'No decisions on this CVE yet.' }}</td>
          </tr>
          <tr v-for="d in shown" :key="d.decision_id" :class="{ 'dec-inactive': d.revoked_at }">
            <!-- an ignore rule gives the finding risk_accepted: it wears that tag -->
            <td><StateTag :state="d.type === 'not_affected' ? 'not_affected' : 'risk_accepted'" /></td>
            <td class="sm">{{ scopeLabel(d) }}</td>
            <td class="sm">
              <span v-if="d.apply_both_scanners" class="both-tag">both</span>
              <ScannerTag v-else-if="d.scanner" :name="d.scanner" />
            </td>
            <td class="sm"><template v-if="(d.approver ?? d.created_by) != null">{{ d.approver ?? d.created_by }}</template><span v-else class="muted-dash">-</span></td>
            <td class="mono-cell sm"><template v-if="d.expiry != null">{{ d.expiry }}</template><span v-else class="muted-dash">-</span></td>
            <td>
              <span v-if="!d.revoked_at" class="dec-active">active</span>
              <span v-else class="dec-revoked">revoked</span>
            </td>
            <td class="c">
              <UiButton
                v-if="canRevoke(d)"
                :disabled="busy"
                title="Revoke this decision (create a new one to replace it)"
                @click="emit('revoke', d.decision_id)"
              >
                Revoke
              </UiButton>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <GridPager
      :total="rows.length"
      :page="page"
      :size="size"
      :shown="shown.length"
      :has-prev="page > 0"
      :has-next="hasNext"
      @prev="page -= 1"
      @next="page += 1"
      @update:size="setSize"
    />
    <div v-if="decisions.length >= 50" class="card-notes">
      <p class="cap-note">Showing the first 50 decisions. Older ones via the Audit screen (M9d).</p>
    </div>
  </DetailCard>
</template>

<style scoped>
.cap-note {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.sm {
  font-size: var(--text-sm);
}
.c {
  text-align: center;
}
.mono-cell {
  font-family: var(--font-mono);
}
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 24px 12px;
}
.dec-inactive td {
  text-decoration: line-through;
  color: var(--soft);
}
.dec-inactive td .both-tag,
.dec-inactive td button {
  text-decoration: none;
}
.dec-active {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--state-resolved-fg);
}
.dec-revoked {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
.both-tag {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  border: 1px solid var(--line);
  border-radius: var(--r-chip);
  padding: 1px 7px;
  color: var(--soft);
}
</style>

<script setup lang="ts">
/**
 * Approvals (M9d slice 4, bolt #38) — the accept-final holder's REVIEW QUEUE over standing
 * risk-acceptances (ruling #30: creation is already SEC-2-gated, so this is not a pending-
 * approval workflow; revoked decisions never appear here). Wire: GET /decisions/approvals —
 * active risk-accepts, soonest-expiring first, server offset paging. The five slice rulings
 * (operator, 2026-07-13): no facet rail v1 · decision-activity lens · row → CVE-searched
 * findings · T<now = limitation notice (the endpoint has no as_of seam) · expiry-warn setting.
 * Route + nav are capability-gated (can_accept_audit_final) since the M9a shell; the CSV
 * export (issue 359) inherits that gate — these rows name who accepted which risk.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { approvalListApiV1DecisionsApprovalsGet, revokeApiV1DecisionsDecisionIdRevokePost } from '@/api/generated'
import { APPROVAL_FIELDS } from '@/approvals/fields.config'
import {
  EXPIRY_WARN_DAYS,
  expiryStatus,
  findingsRoute,
  scannerLabel,
  scopeLabel,
  type ApprovalRow,
} from '@/approvals/viewModel'
import ValueActions from '@/components/filters/ValueActions.vue'
import EditDecisionDialog from '@/components/approvals/EditDecisionDialog.vue'
import ExpiryChip from '@/components/chips/ExpiryChip.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import AuditLens from '@/components/dashboards/AuditLens.vue'
import LimitedHistoricalNotice from '@/components/dashboards/LimitedHistoricalNotice.vue'
import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import RowLink from '@/components/ui/RowLink.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useCsvExport } from '@/composables/useCsvExport'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { activeMode } from '@/filters/fields.config'
import type { FacetsResponse } from '@/filters/facets'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { makeFiltersStore, type FilterMode } from '@/stores/filters'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'
import { refNowMs } from '@/system/clock'
import { lastDataAt } from '@/system/freshness'
import { foreignQuery, ownQuery } from '@/system/globalUrl'
import { readFailureCopy } from '@/findings/failureCopy'

const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()
const route = useRoute()
const router = useRouter()

/* the 4b rail (operator re-ruling on the built 4a screen): one config drives rail + bar +
   URL sync, the audit-screen setup verbatim; every dim is served by the endpoint itself */
const useApprovalFilters = makeFiltersStore('approvals-filters', APPROVAL_FIELDS)
const filters = useApprovalFilters()
filters.fromQuery(route.query)

const rows = ref<ApprovalRow[]>([])
const total = ref(0)
const page = ref(0)
const size = ref(25)
const settled = ref(false)
const failed = ref(false)
const failedStatus = ref<number | null>(null)
const facets = ref<FacetsResponse>({})

/** countdowns measure from the display clock (D28) — wall time at now, T when rewound */
const nowMs = computed(() => refNowMs(timeTravel.t))

/** The scanner column's own value — the `both | trivy | grype` the filter field takes, not
 * the tag's display text (issue 349 §2). */
const scannerValue = (row: ApprovalRow) =>
  row.apply_both_scanners || !row.scanner ? 'both' : row.scanner

/** The mode this exact value is already filtered under, so the active side reads as pressed. */
const cellActive = (fieldKey: string, value: string): FilterMode | null =>
  activeMode(fieldKey, value, filters.selections, filters.modes)

// no as_of in the globals: the queue is now-only (the T<now notice owns the rewound state)
const filterQuery = computed(() =>
  clusterStore.selectedId
    ? buildFilterQuery(
        APPROVAL_FIELDS,
        filters.selections,
        { cluster_id: clusterStore.selectedId },
        filters.modes,
      )
    : null,
)

/* ---- Export CSV (issue 359): useCsvExport owns fetch → blob → download, so a 413/failed
 * response surfaces as a message rather than a broken tab. The request carries `filterQuery`
 * + the same `warn_days` the queue fetched with, so the file is the lens on screen —
 * including which rows count as "expiring" ---- */
const { exporting, run: runExport } = useCsvExport({
  path: '/api/v1/decisions/approvals/export.csv',
  filename: (stamp) => `javv-approvals-${stamp}.csv`,
  event: 'approvals_export_failed',
  onCapped: () => toast.info('Too many rows to export at once. Narrow the filters first.'),
  onFailed: (status) =>
    toast.error(
      status
        ? `Export failed (${status}). Check the backend connection.`
        : 'Export failed. Check the backend connection.',
    ),
  onDone: (name) => toast.success(`Export downloaded · ${name}`),
})

async function exportCsv() {
  const q = filterQuery.value
  if (!q) return
  await runExport({ ...q, warn_days: EXPIRY_WARN_DAYS })
}

let seq = 0
async function fetchQueue() {
  if (!filterQuery.value || !timeTravel.isNow) return
  const mine = ++seq
  const response = await approvalListApiV1DecisionsApprovalsGet({
    query: {
      ...filterQuery.value,
      size: size.value,
      offset: page.value * size.value,
      warn_days: EXPIRY_WARN_DAYS,
    } as never,
  })
  if (mine !== seq) return // a newer read owns the queue now
  failed.value = !response.response?.ok || !response.data
  failedStatus.value = response.response?.status ?? null
  if (!failed.value) {
    const data = response.data as {
      approvals: ApprovalRow[]
      total: number
      facets: Record<string, { key: string; count: number }[]>
    }
    rows.value = data.approvals
    total.value = data.total
    // the endpoint's inline facets → the rail's bucket shape (no per-scanner split here:
    // a decision is the SUBJECT of scanners, not split by them)
    facets.value = Object.fromEntries(
      Object.entries(data.facets).map(([k, buckets]) => [
        k,
        buckets.map((b) => ({ ...b, by_scanner: {} })),
      ]),
    )
  } else {
    logger.warn('approvals_fetch_failed', { status: response.response?.status })
    rows.value = []
  }
  settled.value = true
}
watch(
  [filterQuery, () => timeTravel.isNow, page, size],
  ([q], old) => {
    if (old && JSON.stringify(q) !== JSON.stringify(old[0])) page.value = 0
    void fetchQueue()
  },
  { immediate: true, deep: true },
)

/* selections ⇄ URL (the audit-screen contract: a pasted link reproduces the lens) */
const OWN_KEYS = APPROVAL_FIELDS.map((f) => f.key)
watch(
  () => filters.toQuery(),
  (q) => {
    if (JSON.stringify(q) !== JSON.stringify(ownQuery(route.query, OWN_KEYS)))
      void router.replace({ query: { ...foreignQuery(route.query, OWN_KEYS), ...q } })
  },
)
watch(
  () => route.query,
  (q) => {
    if (JSON.stringify(filters.toQuery()) !== JSON.stringify(ownQuery(q, OWN_KEYS)))
      filters.fromQuery(q)
  },
)

function applySearch(text: string) {
  filters.setText('q', text)
}

/* the decision-activity lens (ruling 2): the journal sliced to entity_type=decision —
   create + revoke are the only decision actions, so one term is the exact slice */
const lensQuery = computed(() =>
  clusterStore.selectedId
    ? { cluster_id: clusterStore.selectedId, entity_type: 'decision', ...timeTravel.asOfParams }
    : null,
)

/* row click (ruling 3): the findings grid searched to the CVE — a decision may be
   cluster-wide, so the grid (not a single finding) is the correct landing */
function openFindings(row: ApprovalRow) {
  logger.debug('approval_row_clicked', { decision_id: row.decision_id })
  void router.push(findingsRoute(row))
}

/* ---- actions: revoke (confirm-in-row) + edit (revoke+new dialog) ---- */
const confirmRevoke = ref<string | null>(null) // decision_id awaiting the second click
const busy = ref(false)
const editing = ref<ApprovalRow | null>(null)

async function revoke(row: ApprovalRow) {
  if (confirmRevoke.value !== row.decision_id) {
    confirmRevoke.value = row.decision_id
    return
  }
  confirmRevoke.value = null
  busy.value = true
  const response = await revokeApiV1DecisionsDecisionIdRevokePost({
    path: { decision_id: row.decision_id },
  })
  busy.value = false
  if (response.response?.ok) {
    logger.info('decision_revoked', { decision_id: row.decision_id })
    toast.success('Acceptance revoked. Its findings return to open on the next projection')
    await fetchQueue()
  } else {
    logger.warn('decision_revoke_failed', { status: response.response?.status })
    toast.error('Revoke failed. Check the backend connection')
  }
}

function onEdited() {
  toast.success('Decision re-issued (revoke + new)')
  void fetchQueue()
}

const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Approvals</h1>
        <p class="head-stat">
          <template v-if="timeTravel.isNow && !failed">{{ fmt(total) }}</template
          ><span v-else class="muted-dash">-</span
          ><span class="head-unit"> standing acceptance{{ total === 1 && timeTravel.isNow && !failed ? '' : 's' }}</span>
        </p>
        <p class="head-note">review queue · active risk-accepts, soonest expiry first · revoked never listed</p>
      </div>
      <AuditLens
        :query="lensQuery"
        title="Decision activity"
        sub="risk-accept creates + revokes journaled in this range. The queue below is current state"
      />
    </div>

    <LimitedHistoricalNotice
      v-if="!timeTravel.isNow"
      title="The approvals queue answers for now"
      body="Standing acceptances are current state: the endpoint has no historical seam yet.
        The decision-activity lens above still rewinds; return to now to review the queue."
    />

    <div v-else class="findings-layout">
      <div class="rail-col">
        <div class="facet-search">
          <AppIcon name="search" :size="14" />
          <input
            :value="filters.selections.q?.[0] ?? ''"
            placeholder="CVE…"
            aria-label="Search acceptances by CVE (contains match)"
            @keydown.enter="applySearch(($event.target as HTMLInputElement).value)"
          />
        </div>
        <FacetRail
          :fields="APPROVAL_FIELDS"
          :selections="filters.selections"
          :facets="facets"
          :modes="filters.modes"
          @toggle="filters.toggle"
          @pick="filters.pickValue"
        />
      </div>

      <div class="findings-main">
        <div class="toolbar-row">
          <FilterBar
            :fields="APPROVAL_FIELDS"
            :selections="filters.selections"
            :modes="filters.modes"
            :facets="facets"
            @toggle="filters.toggle"
            @set-text="filters.setText"
            @set-mode="filters.setMode"
            @toggle-mode="filters.toggleMode"
            @clear-field="filters.clearField"
            @clear-all="filters.clearAll"
          />
          <UiButton
            variant="control"
            :disabled="exporting || rows.length === 0"
            @click="exportCsv"
          >
            <AppIcon name="download" :size="13" />{{
              exporting ? 'Exporting…' : 'Export approvals (CSV)'
            }}
          </UiButton>
        </div>

      <UiSkeleton v-if="!settled" :height="220" label="Loading approvals" class="skel-gap" />
      <p v-else-if="failed" class="load-error" role="alert">
        {{ readFailureCopy(failedStatus, 'Could not load the queue. Check the backend connection.') }}
      </p>
      <section v-else class="card queue-card">
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
              <tr v-for="row in rows" :key="row.decision_id" @click="openFindings(row)">
                <td>
                  <RowLink :to="findingsRoute(row)" @open="openFindings(row)"><span class="mono-cell strong nowrap cve-link">{{ row.cve_id }}</span></RowLink>
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
                      @pick="(m) => filters.pickValue('scanner', scannerValue(row), m)"
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
                      @pick="(m) => filters.pickValue('approver', row.created_by, m)"
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
                      @pick="(m) => filters.pickValue('status', expiryStatus(row.expiry, nowMs), m)"
                    />
                  </span>
                </td>
                <td class="fit">
                  <span class="mono-cell sm nowrap" :title="row.created_at">{{ lastDataAt(row.created_at) }}</span>
                </td>
                <td class="fit row-actions" @click.stop>
                  <UiButton variant="mini" :disabled="busy" @click="editing = row">Edit</UiButton>
                  <UiButton
                    variant="mini"
                    :class="{ 'revoke-armed': confirmRevoke === row.decision_id }"
                    :disabled="busy"
                    @click="revoke(row)"
                  >
                    {{ confirmRevoke === row.decision_id ? 'Confirm revoke' : 'Revoke' }}
                  </UiButton>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="rows.length === 0" class="empty-row">
          {{
            Object.values(filters.selections).some((v) => v.length > 0)
              ? 'No acceptances match these filters.'
              : 'No standing risk-acceptances. Accepted findings land here for review.'
          }}
        </div>
        <GridPager
          :total="total"
          :page="page"
          :size="size"
          :shown="rows.length"
          :has-prev="page > 0"
          :has-next="(page + 1) * size < total"
          @prev="page = Math.max(0, page - 1)"
          @next="page = page + 1"
          @update:size="(s) => { size = s; page = 0 }"
        />
      </section>
      </div>
    </div>

    <EditDecisionDialog
      v-if="editing"
      :decision="editing"
      @close="editing = null"
      @edited="onEdited"
    />
  </div>
</template>

<style scoped>
.queue-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
  margin-top: 16px;
}
.queue-card .tbl th:first-child,
.queue-card .tbl td:first-child {
  padding-left: 16px;
}
/* link affordance on the identifier, the findings-grid grammar */
.queue-card :deep(.cve-link) {
  transition: color 0.12s ease-out;
}
.queue-card .tbl-hover tbody tr:hover :deep(.cve-link) {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .queue-card :deep(.cve-link) {
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
.skel-gap {
  margin-top: 16px;
}
.load-error {
  margin-top: 16px;
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
</style>

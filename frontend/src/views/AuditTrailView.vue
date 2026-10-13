<script setup lang="ts">
/**
 * Audit log screen (M9d slice 1; SCREENS §10): the D32 stream on the prototype's table
 * grammar (screens-audit.jsx, operator ruling 2026-07-12) behind the shared M9a filter module
 * — one AUDIT_FIELDS config drives FacetRail + FilterBar, selections URL-synced; counts come
 * live from GET /api/v1/audit/facets. The grid is the shared cursor-stack pager (GridPager)
 * over GET /api/v1/audit; every read carries cluster_id + as_of (D28: a rewound T bounds the
 * log). Click-through only where entity_type=="finding" (A-5), through the row's read-time
 * decoration — an aged-out finding row stays inert and accurate.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { auditFacetsApiV1AuditFacetsGet, readAuditLogApiV1AuditGet } from '@/api/generated'
import type {
  AuditFacetsApiV1AuditFacetsGetData,
  ReadAuditLogApiV1AuditGetData,
} from '@/api/generated'
import { AUDIT_FIELDS } from '@/audit/fields.config'
import AuditTable from '@/components/audit/AuditTable.vue'
import AuditLens from '@/components/dashboards/AuditLens.vue'
import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useApi } from '@/composables/useApi'
import { useCsvExport } from '@/composables/useCsvExport'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { readFailureCopy } from '@/findings/failureCopy'
import type { FacetsResponse } from '@/filters/facets'
import { logger } from '@/lib/logger'
import { useAuditStore, type AuditEvent } from '@/stores/audit'
import { useClusterStore } from '@/stores/cluster'
import { makeFiltersStore } from '@/stores/filters'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'
import { foreignQuery, ownQuery } from '@/system/globalUrl'

const useAuditFilters = makeFiltersStore('audit-filters', AUDIT_FIELDS)
const filters = useAuditFilters()
const grid = useAuditStore()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const { withGlobals } = useApi()
const route = useRoute()
const router = useRouter()

filters.fromQuery(route.query)

/* ---- facets (M9a module; audit rework — live rail counts) ---- */
const facets = ref<FacetsResponse>({})
const facetsFailed = ref(false)
const facetsFailedStatus = ref<number | null>(null)

const facetsQuery = computed(() =>
  clusterStore.selectedId
    ? buildFilterQuery(AUDIT_FIELDS, filters.selections, withGlobals(), filters.modes)
    : null,
)

let facetsSeq = 0
async function loadFacets(q: typeof facetsQuery.value) {
  if (!q) return
  const mine = ++facetsSeq
  const response = await auditFacetsApiV1AuditFacetsGet({
    query: q as AuditFacetsApiV1AuditFacetsGetData['query'],
  })
  if (mine !== facetsSeq) return // a newer read owns the rail now
  if (response.response?.ok && response.data) {
    facets.value = (response.data as { facets: FacetsResponse }).facets
    facetsFailed.value = false
  } else {
    facetsFailed.value = true
    facetsFailedStatus.value = response.response?.status ?? null
    logger.warn('audit_facets_failed', { status: response.response?.status })
  }
}
watch(facetsQuery, (q) => void loadFacets(q), { immediate: true })

/* ---- table rows: cursor-stack paging, same contract as the findings grid ---- */
// filters or globals changed → any held cursor belongs to the old query: back to page 0
watch(facetsQuery, (q, old) => {
  if (old && JSON.stringify(q) !== JSON.stringify(old)) grid.resetPaging()
})
// cluster/T switched → the held rows are another tenant's/world's; readable-but-stale rows
// under a slow network misled the issue-431 §4 walk, so drop them, don't just re-page
watch(
  () => [clusterStore.selectedId, timeTravel.t],
  () => grid.clearResults(),
)

const rowsQuery = computed(() => {
  if (!clusterStore.selectedId) return null
  const q = buildFilterQuery(AUDIT_FIELDS, filters.selections, withGlobals(), filters.modes)
  return { ...q, size: grid.size, ...(grid.activeCursor ? { cursor: grid.activeCursor } : {}) }
})

let rowsSeq = 0
async function loadRows(q: typeof rowsQuery.value) {
  if (!q) return
  const mine = ++rowsSeq
  grid.loading = true
  const response = await readAuditLogApiV1AuditGet({
    query: q as ReadAuditLogApiV1AuditGetData['query'],
  })
  if (mine !== rowsSeq) return // a newer read owns the grid now
  grid.loading = false
  if (response.response?.ok && response.data) {
    const body = response.data as unknown as {
      data: AuditEvent[]
      total: { value: number; relation: string }
      next_cursor: string | null
    }
    grid.setResult(body.data, body.total, body.next_cursor)
  } else {
    // a refused later page stays where it is, so Prev still leads back (issue 833, G1)
    grid.setFailed(response.response?.status ?? null)
    logger.warn('audit_load_failed', { status: response.response?.status, page: grid.page })
  }
}

// the rows' failure names the whole log; the counts alone failing leaves the rows standing
const failureMessage = computed(() =>
  grid.failed
    ? readFailureCopy(grid.failedStatus, 'Audit log unavailable. Check the backend connection, then retry.')
    : `Filter counts could not be loaded. ${readFailureCopy(facetsFailedStatus.value, 'Check the backend connection.')}`,
)
watch(
  rowsQuery,
  (q, old) => {
    if (JSON.stringify(q) === JSON.stringify(old)) return
    void loadRows(q)
  },
  { immediate: true },
)

/* ---- URL sync (M9a); rewrite only this screen's own keys — foreign params survive ---- */
const OWN_KEYS = AUDIT_FIELDS.map((f) => f.key)
watch(
  () => filters.toQuery(),
  (q) => {
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

/* ---- click-through (A-5): the row's decoration carries the finding's identity ---- */
function findingRoute(row: AuditEvent) {
  const f = row.finding
  if (!f) return null
  return {
    name: 'finding',
    params: { cveId: f.cve_id },
    query: {
      digest: String(f.image_digest ?? ''),
      scanner: f.scanner ?? '',
      pkg: f.package_name ?? '',
    },
  }
}
function openFinding(row: AuditEvent) {
  const to = findingRoute(row)
  if (!to) return
  logger.debug('audit_row_clicked', { finding_key: row.entity_id })
  void router.push(to)
}

const totalLabel = computed(
  () => `${grid.total.toLocaleString('en-US')}${grid.totalIsLowerBound ? '+' : ''}`,
)

/* ---- Export CSV (prototype screen-head action): fetch → blob → download, so a 413/failed
 * response surfaces as a message, not a broken tab (the ExportDialog pattern) ---- */
const toast = useToastStore()
const { exporting, run: runExport } = useCsvExport({
  path: '/api/v1/audit/export.csv',
  filename: (stamp) => `javv-audit-${stamp}.csv`,
  event: 'audit_export_failed',
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
  const q = facetsQuery.value
  if (!q) return
  await runExport(q)
}
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Audit log</h1>
        <p class="head-stat">
          <template v-if="grid.totalKnown">{{ totalLabel }}</template
          ><span v-else class="muted-dash">-</span><span class="head-unit"> events</span>
        </p>
        <p class="head-note">immutable, per user · window bounded by audit-log retention</p>
      </div>
      <AuditLens :query="facetsQuery" />
    </div>

    <div class="findings-layout">
      <div class="rail-col">
        <FacetRail
          :fields="AUDIT_FIELDS"
          :selections="filters.selections"
          :facets="facets"
          :counts-unknown="facetsFailed"
          :modes="filters.modes"
          @toggle="filters.toggle"
          @pick="filters.pickValue"
        />
      </div>

      <div class="findings-main">
        <div class="toolbar-row">
          <FilterBar
            :fields="AUDIT_FIELDS"
            :selections="filters.selections"
            :modes="filters.modes"
            :facets="facets"
            :counts-unknown="facetsFailed"
            @toggle="filters.toggle"
            @set-text="filters.setText"
            @set-mode="filters.setMode"
            @toggle-mode="filters.toggleMode"
            @clear-field="filters.clearField"
            @clear-all="filters.clearAll"
          />
          <UiButton variant="control" :disabled="exporting" @click="exportCsv">
            <AppIcon name="download" :size="13" />{{ exporting ? 'Exporting…' : 'Export CSV' }}
          </UiButton>
        </div>

        <p v-if="grid.failed || facetsFailed" class="load-error" role="alert">
          {{ failureMessage }}
        </p>

        <div class="tbl-card">
        <AuditTable
          :rows="grid.rows"
          :loading="grid.loading"
          :failed="grid.failed"
          :filtered="filters.hasFilters"
          :selections="filters.selections"
          :modes="filters.modes"
          :row-to="findingRoute"
          @row-click="openFinding"
          @pick-value="filters.pickValue"
        />
        <GridPager
          :total="grid.total"
          :page="grid.page"
          :size="grid.size"
          :shown="grid.rows.length"
          :failed="grid.failed"
          :has-prev="grid.hasPrev"
          :has-next="grid.hasNext"
          @prev="grid.goPrev()"
          @next="grid.goNext()"
          @update:size="grid.setSize"
        />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* head/layout/toolbar scaffolding lives in base.css (shared data-screen grammar) */
.load-error {
  margin: 0 0 10px;
}
</style>

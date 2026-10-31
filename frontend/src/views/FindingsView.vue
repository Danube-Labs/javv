<script setup lang="ts">
/**
 * Findings screen (M9a filter module + M9b grid): one FINDINGS_FIELDS config drives FacetRail +
 * FilterBar, selections URL-synced; the lazy grid renders exactly what
 * `GET /api/v1/findings` returns (cursor paging, server total). Facet counts live from
 * `GET /api/v1/findings/facets`. Everything carries cluster_id + as_of; grid queries add
 * present=true. Detail panel + triage land in the next M9b slices.
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'

import { closeUnpaged } from '@/api/cursors'
import { facetFindingsApiV1FindingsFacetsGet, searchFindingsApiV1FindingsGet } from '@/api/generated'
import type {
  FacetFindingsApiV1FindingsFacetsGetData,
  SearchFindingsApiV1FindingsGetData,
} from '@/api/generated'
import SevChip from '@/components/chips/SevChip.vue'
import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import ColumnsMenu from '@/components/findings/ColumnsMenu.vue'
import ExportDialog from '@/components/findings/ExportDialog.vue'
import SaveViewDialog from '@/components/findings/SaveViewDialog.vue'
import BulkTriageBar from '@/components/triage/BulkTriageBar.vue'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import GridPager from '@/components/findings/GridPager.vue'
import UiSearchBox from '@/components/ui/UiSearchBox.vue'
import { useApi } from '@/composables/useApi'
import { findingsValueSearch } from '@/composables/useValueSearch'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import type { FacetsResponse } from '@/filters/facets'
import { FINDINGS_EXCLUSIVE_PAIRS, FINDINGS_FIELDS, MAX_FILTER_VALUES } from '@/filters/fields.config'
import { buildFindingsQuery } from '@/findings/buildFindingsQuery'
import { FINDINGS_COLUMNS } from '@/findings/columns'
import { PAST_TIME_UNRECORDED_KEYS, hasAssigneeWithUnassigned } from '@/findings/exportParams'
import { captureLens } from '@/findings/savedViews'
import { reorderFromDrag, restoreHidden, restoreOrder } from '@/system/columnOrder'
import { FAILURE_COPY, failureKind, readFailureCopy, type FailureKind } from '@/findings/failureCopy'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useFindingsStore, type FindingRow } from '@/stores/findings'
import { makeFiltersStore } from '@/stores/filters'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'
import { foreignQuery, ownQuery } from '@/system/globalUrl'

const useFindingsFilters = makeFiltersStore(
  'findings-filters',
  FINDINGS_FIELDS,
  MAX_FILTER_VALUES,
  FINDINGS_EXCLUSIVE_PAIRS,
)
const filters = useFindingsFilters()
const auth = useAuthStore()
const clusterStore = useClusterStore()
const grid = useFindingsStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()
const { withGlobals } = useApi()
const route = useRoute()
const router = useRouter()

const facets = ref<FacetsResponse>({})
const facetsFailed = ref(false)
const facetsFailedStatus = ref<number | null>(null)

filters.fromQuery(route.query)

/* ---- facets (M9a) ---- */
// window_days feeds ONLY the "new in range" flag; changing the picker window re-fires both
// reads while that flag is on (the computed tracks the store)
const filterGlobals = () => ({ ...withGlobals(), window_days: timeTravel.windowDays })
const facetsQuery = computed(() =>
  clusterStore.selectedId
    ? buildFilterQuery(FINDINGS_FIELDS, filters.selections, filterGlobals(), filters.modes)
    : null,
)

let facetsSeq = 0
const UNRECORDED = new Set<string>(PAST_TIME_UNRECORDED_KEYS)
async function loadFacets(q: typeof facetsQuery.value) {
  if (!q) return
  const mine = ++facetsSeq
  const response = await facetFindingsApiV1FindingsFacetsGet({
    // builder output is a generic param record; the endpoint type is the precise contract
    query: q as FacetFindingsApiV1FindingsFacetsGetData['query'],
  })
  if (mine !== facetsSeq) return // a newer read owns the rail now
  if (response.response?.ok && response.data) {
    const counts = (response.data as { facets: FacetsResponse }).facets
    // the scan history does not record these, so at a past time their empty lists are no
    // counts, not counts of 0: left out, they show no count (issue 980)
    facets.value = q.as_of
      ? Object.fromEntries(Object.entries(counts).filter(([key]) => !UNRECORDED.has(key)))
      : counts
    facetsFailed.value = false
  } else {
    facetsFailed.value = true
    facetsFailedStatus.value = response.response?.status ?? null
    logger.warn('findings_facets_failed', { status: response.response?.status })
  }
}
watch(facetsQuery, (q) => void loadFacets(q), { immediate: true })
// a value past the top 32 of a list: the menu asks for it under the same filters (issue 1064)
const searchValues = findingsValueSearch(() => facetsQuery.value)

/* ---- grid rows (M9b) ---- */
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

const rowsQuery = computed(() =>
  clusterStore.selectedId
    ? buildFindingsQuery(
        FINDINGS_FIELDS,
        filters.selections,
        filterGlobals(),
        { sort: grid.sort, order: grid.order, size: grid.size, cursor: grid.activeCursor },
        filters.modes,
      )
    : null,
)

let rowsSeq = 0
// read from the refused query itself, so a change of time or filter while the next read runs
// cannot change the reason shown for this one. The grid store keeps a refusal across a remount,
// so the first value comes from what that store and the filters still hold.
const failedKind = ref<FailureKind>(
  failureKind(grid.failedStatus, timeTravel.t !== null, hasAssigneeWithUnassigned(rowsQuery.value ?? {})),
)
async function loadRows(q: typeof rowsQuery.value) {
  if (!q) return
  const mine = ++rowsSeq
  grid.loading = true
  // keep_open: the last page keeps its search, so Prev from it works (the pager closes the walk)
  const response = await searchFindingsApiV1FindingsGet({
    query: { ...q, keep_open: true } as SearchFindingsApiV1FindingsGetData['query'],
  })
  const live = !q.as_of // a past-T page holds no search on the server
  if (mine !== rowsSeq) {
    // a newer read owns the grid now; a first page it replaced opened a walk nobody will page
    if (!q.cursor) closeUnpaged(response.data?.next_cursor, live)
    return
  }
  grid.loading = false
  if (response.response?.ok && response.data) {
    const body = response.data as {
      data: FindingRow[]
      total: { value: number }
      next_cursor: string | null
    }
    grid.setResult(body.data, body.total.value, body.next_cursor, live)
    grid.failed = false
    grid.failedStatus = null
  } else {
    // a refused later page stays where it is, so Prev still leads back (issue 833, G1)
    const status = response.response?.status ?? null
    failedKind.value = failureKind(status, Boolean(q.as_of), hasAssigneeWithUnassigned(q))
    grid.setFailed(status)
    logger.warn('findings_search_failed', { status: response.response?.status, page: grid.page })
  }
}
// the rows' failure names the whole grid; the counts alone failing leaves the rows standing (F9)
const failureMessage = computed(() =>
  grid.failed
    ? FAILURE_COPY[failedKind.value]
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
// opening a finding keeps the walk, so Back lands on the same page; leaving for any other screen
// closes it, and the grid comes back on page 1 with its filters and sort (ruling on issue 832)
let keepWalk = false
onBeforeRouteLeave((to) => {
  keepWalk = to.name === 'finding'
})
onUnmounted(() => {
  if (!keepWalk) grid.clearResults()
})

/** A bulk apply changed rows under the current lens — reload both surfaces in place. */
function applySearch(value: string) {
  const text = value.trim()
  if (text.length === 1) {
    toast.info('Search needs at least 2 characters.')
    return
  }
  filters.setText('q', value)
}

function refreshAfterBulk(count: number) {
  toast.success(`Bulk triage applied · ${count.toLocaleString('en-US')} findings`)
  grid.resetPaging()
  void loadRows(rowsQuery.value)
  void loadFacets(facetsQuery.value)
}

/* ---- URL sync (M9a); the rewrite touches only this screen's own keys — globals and any
   foreign param survive (ownership split, operator order 2026-07-17) ---- */
const OWN_KEYS = FINDINGS_FIELDS.map((f) => f.key)
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

/** One definition of where a row leads: the row click pushes it, the id link carries it as href. */
function findingRoute(row: FindingRow) {
  return {
    name: 'finding',
    params: { cveId: row.cve_id },
    // identity = (cve_id, image_digest); scanner + package keep continuity with the clicked row
    query: {
      digest: String(row.image_digest ?? ''),
      scanner: row.scanner,
      pkg: row.package_name,
      ver: row.installed_version ?? '',
    },
  }
}
function openFinding(row: FindingRow) {
  logger.debug('finding_row_clicked', { finding_key: row.finding_key })
  void router.push(findingRoute(row))
}

/* ---- column visibility + density (Columns menu), persisted per browser ---- */
const COLS_KEY = 'javv.findings.hidden_cols'
const DENSE_KEY = 'javv.findings.dense'
const COL_KEYS = FINDINGS_COLUMNS.map(([key]) => key)
// first-run default hides the low-signal columns (operator 2026-07-11: KEV mostly empty,
// versions live in the detail view; last_scan is the hidden sibling of first_seen) — the
// Columns menu + localStorage override per user
const hiddenCols = ref<Set<string>>(
  restoreHidden(localStorage.getItem(COLS_KEY), COL_KEYS, ['epss', 'kev', 'current', 'fixed', 'last_scan']),
)
const dense = ref(localStorage.getItem(DENSE_KEY) !== 'false')

function toggleCol(key: string) {
  const next = new Set(hiddenCols.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  hiddenCols.value = next
  localStorage.setItem(COLS_KEY, JSON.stringify([...next]))
}
function setDense(value: boolean) {
  dense.value = value
  localStorage.setItem(DENSE_KEY, String(value))
}

/* ---- column order (task 92): header drag + Columns-menu drag, one persisted order ---- */
const ORDER_KEY = 'javv.findings.col_order'
const colOrder = ref<string[]>(restoreOrder(localStorage.getItem(ORDER_KEY), COL_KEYS))
const orderedCols = computed(() =>
  colOrder.value.map((key) => FINDINGS_COLUMNS.find(([k]) => k === key)!),
)

/* ---- saved-view capture (M9f slice 4): the CURRENT workbench, ready to name ---- */
const capturedPreset = computed(() =>
  captureLens(FINDINGS_FIELDS, filters.selections, filters.modes, timeTravel.windowDays),
)
const capturedWorkbench = computed(() => ({
  columns: colOrder.value.filter((k) => !hiddenCols.value.has(k)),
  dense: dense.value,
  sort: grid.sort,
  order: grid.order,
  // relative window only — never the absolute t (cluster-agnostic capture, schema v2)
  window_days: timeTravel.windowDays,
}))

function setColOrder(next: string[]) {
  colOrder.value = next
  localStorage.setItem(ORDER_KEY, JSON.stringify(next))
}
function onHeaderReorder(dragIndex: number, dropIndex: number) {
  // 2 = the pinned Vulnerability + Severity columns the PrimeVue indexes count past
  const next = reorderFromDrag(colOrder.value, hiddenCols.value, dragIndex, dropIndex, 2)
  if (next) setColOrder(next)
}
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Findings</h1>
        <p class="head-stat">
          <!-- a count before the first read, or after a refused one, is not zero: it is unknown -->
          <template v-if="grid.totalKnown">{{ grid.total.toLocaleString('en-US') }}</template
          ><span v-else class="muted-dash">-</span><span class="head-unit"> findings</span>
        </p>
        <p class="head-note">kept per-scanner, no cross-merge</p>
      </div>
      <IngestLens v-if="clusterStore.selectedId" :cluster-id="clusterStore.selectedId" />
    </div>

    <div class="findings-layout">
      <div class="rail-col">
        <UiSearchBox
          card
          :model-value="filters.selections.q?.[0] ?? ''"
          placeholder="CVE, image, namespace…"
          aria-label="Search findings (contains match)"
          @keydown.enter="applySearch(($event.target as HTMLInputElement).value)"
        />
      <FacetRail
        :fields="FINDINGS_FIELDS"
        :selections="filters.selections"
        :facets="facets"
        :counts-unknown="facetsFailed"
        :modes="filters.modes"
        :max-values="MAX_FILTER_VALUES"
        :search-values="searchValues"
        @toggle="filters.toggle"
        @pick="filters.pickValue"
      >
        <template #value="{ field, value, label }">
          <SevChip v-if="field.key === 'severity'" :level="value" :dot="true" />
          <template v-else>{{ label }}</template>
        </template>
      </FacetRail>
      </div>

      <div class="findings-main">
        <div class="toolbar-row">
          <FilterBar
            :fields="FINDINGS_FIELDS"
            :selections="filters.selections"
            :modes="filters.modes"
            :facets="facets"
            :counts-unknown="facetsFailed"
            :max-values="MAX_FILTER_VALUES"
            :search-values="searchValues"
            @toggle="filters.toggle"
            @set-text="filters.setText"
            @set-mode="filters.setMode"
            @toggle-mode="filters.toggleMode"
            @clear-field="filters.clearField"
            @clear-all="filters.clearAll"
          />
          <SaveViewDialog :preset="capturedPreset" :workbench="capturedWorkbench" />
          <ExportDialog
            :fields="FINDINGS_FIELDS"
            :selections="filters.selections"
            :modes="filters.modes"
            :historical="timeTravel.t !== null"
          />
          <BulkTriageBar
            :fields="FINDINGS_FIELDS"
            :selections="filters.selections"
            :modes="filters.modes"
            :total="grid.totalKnown ? grid.total : null"
            :can-triage="auth.hasCapability('can_triage')"
            :can-accept-final="auth.hasCapability('can_accept_audit_final')"
            :historical="timeTravel.t !== null"
            @applied="refreshAfterBulk"
          />
          <ColumnsMenu
            :cols="orderedCols"
            :hidden="hiddenCols"
            :dense="dense"
            reorderable
            @toggle-col="toggleCol"
            @update:dense="setDense"
            @reorder="setColOrder"
          />
        </div>
        <p v-if="grid.failed || facetsFailed" class="load-error" role="alert">
          {{ failureMessage }}
        </p>
        <div class="tbl-card">
        <FindingsTable
          :rows="grid.rows"
          :sort="grid.sort"
          :order="grid.order"
          :loading="grid.loading"
          :settled="grid.settled"
          :failed="grid.failed"
          :hidden="hiddenCols"
          :col-order="colOrder"
          :selections="filters.selections"
          :modes="filters.modes"
          reorderable
          @pick-value="filters.pickValue"
          :dense="dense"
          :filtered="Object.values(filters.selections).some((v) => v.length > 0)"
          :row-to="findingRoute"
          @sort="grid.setSort"
          @row-click="openFinding"
          @reorder="onHeaderReorder"
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

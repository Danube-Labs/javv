<script setup lang="ts">
/**
 * The findings grid (prototype screens-findings.jsx table + `.tbl` CSS; D27): PrimeVue
 * DataTable in LAZY mode — it renders exactly the rows the server returned; sorting emits an
 * event and the parent refetches. Nothing is sorted, counted, or paged client-side.
 *
 * Sortable columns = the server's sort whitelist only (severity_rank, epss — bolt README
 * 2026-07-09); the prototype's client-side sort on cve/state/assignee has no server field.
 * Per-scanner rows are distinct (one scanner tag per row, disagree flagged) — never merged.
 *
 * Column order (task 92): the toggleable columns render from `colOrder`; Vulnerability +
 * Severity alone stay pinned left (row identity — operator unpinned State 2026-07-11). With
 * `reorderable`, headers drag (discover-grid grammar) — the table emits raw PrimeVue indexes and
 * the OWNER maps + persists them (`system/columnOrder.ts`), same parent-owns-state
 * discipline as `hidden`.
 */
import Column from 'primevue/column'
import DataTable, {
  type DataTableColumnReorderEvent,
  type DataTableSortEvent,
} from 'primevue/datatable'
import { computed, nextTick, ref, watch } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import EpssBar from '@/components/chips/EpssBar.vue'
import KevTag from '@/components/chips/KevTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import SlaCell from '@/components/chips/SlaCell.vue'
import StateTag from '@/components/chips/StateTag.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import ValueActions from '@/components/filters/ValueActions.vue'
import RowLink from '@/components/ui/RowLink.vue'
import type { SortField, SortOrder } from '@/findings/buildFindingsQuery'
import { FINDINGS_COLUMNS, type FindingsColumnKey } from '@/findings/columns'
import { stateLabel } from '@/findings/stateLabels'
import { activeMode, type Selections } from '@/filters/fields.config'
import type { FilterMode, Modes } from '@/stores/filters'
import type { FindingRow } from '@/stores/findings'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { refNowMs } from '@/system/clock'
import { lastDataAt } from '@/system/freshness'

const props = withDefaults(
  defineProps<{
    rows: FindingRow[]
    sort: SortField
    order: SortOrder
    loading: boolean
    /** a read has come back at least once; before that the grid has no answer to report */
    settled?: boolean
    /** the read was refused: the grid has no answer, so it must not say "no findings" */
    failed?: boolean
    /** keys from FINDINGS_COLUMNS hidden via the Columns menu (cve/severity/state are fixed) */
    hidden?: ReadonlySet<string>
    /** FINDINGS_COLUMNS keys in display order (hidden keys keep their slot) */
    colOrder?: readonly string[]
    /** header drag-reorder on; the parent owns + persists the order */
    reorderable?: boolean
    dense?: boolean
    /** any filter active? drives filtered-empty vs first-run empty copy */
    filtered?: boolean
    /** active selections + modes, so a cell action can show which side it already sits on */
    selections?: Selections
    modes?: Modes
    /** where a row leads: its identifier renders as a real link, so the keyboard can open it */
    rowTo?: (row: FindingRow) => RouteLocationRaw
  }>(),
  {
    hidden: () => new Set<string>(),
    colOrder: () => FINDINGS_COLUMNS.map(([key]) => key),
    reorderable: false,
    dense: true,
    filtered: false,
  },
)

/** rendered orderable columns: display order minus the hidden set */
const orderedKeys = computed(
  () => props.colOrder.filter((k) => !props.hidden.has(k)) as FindingsColumnKey[],
)

const timeTravel = useTimeTravelStore()
/** the D28 display clock: SLA countdowns measure from T when rewound, never from today */
const slaNowMs = computed(() => refNowMs(timeTravel.t))

const COL_HEADER: Record<FindingsColumnKey, string> = {
  first_seen: 'First seen',
  last_scan: 'Last scan',
  epss: 'EPSS',
  kev: 'KEV',
  package: 'Package',
  current: 'Current',
  fixed: 'Fixed',
  image: 'Image',
  namespace: 'Namespace',
  images: 'Affected',
  scanner: 'Scanner',
  sla: 'SLA',
  state: 'State',
  assignee: 'Assignee',
}
// every cell left-anchored (operator 2026-07-11: we read left to right — no r/c columns);
// narrow data columns shrink to content so layout slack pools in the text columns
const FIT_COLS = new Set<FindingsColumnKey>([
  'first_seen',
  'last_scan',
  'epss',
  'kev',
  'current',
  'fixed',
  'images',
  'scanner',
  'sla',
  'state',
  'assignee',
])
const colClass = (key: FindingsColumnKey) =>
  [FIT_COLS.has(key) ? 'fit' : '', props.reorderable ? 'th-drag' : ''].join(' ').trim()

// the server's sort whitelist, column → field (severity_rank rides the pinned column)
const SORT_FIELD: Partial<Record<FindingsColumnKey, SortField>> = {
  first_seen: 'first_seen_at',
  last_scan: 'last_scan_at',
  epss: 'epss',
}

const emit = defineEmits<{
  sort: [field: SortField]
  rowClick: [row: FindingRow]
  /** raw PrimeVue rendered-column indexes — map with reorderFromDrag(pinnedLeft=2) */
  reorder: [dragIndex: number, dropIndex: number]
  /** a cell's value action (issue 349 §2): filter TO / OUT of this exact value */
  pickValue: [fieldKey: string, value: string, mode: FilterMode]
}>()

function onSort(e: DataTableSortEvent) {
  if (typeof e.sortField === 'string') emit('sort', e.sortField as SortField)
}
const dt = ref<InstanceType<typeof DataTable> | null>(null)

// PrimeVue tracks its own column order (d_columnOrder) in parallel and renders BY IT once
// reorderable: an order change arriving from outside (the Columns-menu drag) would not show,
// and a header drop onto a reorderable-column=false pin (PrimeVue only blocks the DRAG side)
// could violate the pins. `colOrder` is the truth — re-assert it on every change and drop.
function syncPrimeOrder() {
  const inst = dt.value as unknown as { d_columnOrder?: string[] } | null
  if (inst) inst.d_columnOrder = ['cve', 'severity', ...orderedKeys.value]
}
watch(orderedKeys, () => void nextTick(syncPrimeOrder))

async function onColReorder(e: DataTableColumnReorderEvent) {
  emit('reorder', e.dragIndex, e.dropIndex)
  await nextTick()
  syncPrimeOrder()
}

const shortImage = (r: FindingRow) => `${(r.image_repo ?? '').split('/').pop()}${r.tag ? ':' + r.tag : ''}`
const nsLabel = (r: FindingRow): string => {
  const ns = Array.isArray(r.namespaces) ? (r.namespaces as string[]) : []
  if (ns.length === 0) return '-'
  return ns.length === 1 ? ns[0]! : `${ns[0]} +${ns.length - 1}`
}

/**
 * Cell value actions (issue 349 §2). A column earns the affordance only where the value it
 * shows is EXACTLY the value a negatable filter field takes — anything looser would build a
 * filter that doesn't mean what the cell says.
 *
 * `image` filters on the row's FULL `image_repo` (an exact `term` server-side) even though the
 * cell shortens it for display — and on repo only, since findings carry no tag filter, which
 * the action's label says out loud.
 *
 * `cve` and `package` joined in issue 492, once their params existed — `package` filters
 * `package_name`, which is the package itself and not `ptype` (that is the package's TYPE).
 * Deliberately absent: the pure-data columns. `namespace` only qualifies on a single-namespace
 * row, because a finding spanning three namespaces has no one value to filter on.
 */
const CELL_FILTER_FIELD: Partial<Record<FindingsColumnKey | 'severity' | 'cve', string>> = {
  severity: 'severity',
  state: 'state',
  scanner: 'scanner',
  namespace: 'namespace',
  assignee: 'assignee',
  image: 'image',
  cve: 'cve',
  package: 'package',
}

function cellValue(key: string, r: FindingRow): string | null {
  if (key === 'severity') return r.severity_canonical ?? null
  if (key === 'state') return r.state ?? null
  if (key === 'scanner') return r.scanner ?? null
  if (key === 'assignee') return r.assignee || null
  if (key === 'image') return r.image_repo || null
  if (key === 'cve') return r.cve_id || null
  // the cell shows package AND type; only the package name has a filter twin
  if (key === 'package') return r.package_name || null
  if (key === 'namespace') {
    const ns = Array.isArray(r.namespaces) ? (r.namespaces as string[]) : []
    return ns.length === 1 ? ns[0]! : null // ambiguous across several — no true single value
  }
  return null
}

/** The mode this exact value is already filtered under, so the active side reads as pressed. */
const cellActive = (key: string, value: string): FilterMode | null =>
  activeMode(CELL_FILTER_FIELD[key as FindingsColumnKey] ?? '', value, props.selections, props.modes)
</script>

<template>
  <div class="tbl-wrap">
    <DataTable
      ref="dt"
      :value="props.rows"
      lazy
      :sort-field="props.sort"
      :sort-order="props.order === 'desc' ? -1 : 1"
      :loading="props.loading"
      data-key="finding_key"
      :reorderable-columns="props.reorderable"
      :pt="{ table: { class: `tbl tbl-hover ${props.dense ? 'tbl-dense' : ''} ${props.reorderable ? 'tbl-reorder' : ''}` } }"
      @sort="onSort"
      @column-reorder="onColReorder"
      @row-click="(e) => emit('rowClick', e.data as FindingRow)"
    >
      <Column column-key="cve" header="Vulnerability" :reorderable-column="false">
        <template #body="{ data }">
          <span class="cell-actionable">
            <RowLink v-if="props.rowTo" :to="props.rowTo(data)" @open="emit('rowClick', data)">
              <span class="mono-cell strong nowrap cve-link">{{ data.cve_id }}</span>
            </RowLink>
            <span v-else class="mono-cell strong nowrap cve-link">{{ data.cve_id }}</span>
            <ValueActions
              v-if="cellValue('cve', data)"
              class="val-act-reveal"
              field="CVE"
              :value="cellValue('cve', data)!"
              :active="cellActive('cve', cellValue('cve', data)!)"
              @pick="(m) => emit('pickValue', 'cve', cellValue('cve', data)!, m)"
            />
          </span>
        </template>
      </Column>
      <Column column-key="severity" field="severity_rank" header="Severity" sortable :reorderable-column="false" class="fit">
        <template #body="{ data }">
          <span class="cell-actionable">
            <SevChip :level="data.severity_canonical" />
            <ValueActions
              v-if="cellValue('severity', data)"
              class="val-act-reveal"
              field="Severity"
              :value="cellValue('severity', data)!"
              :active="cellActive('severity', cellValue('severity', data)!)"
              @pick="(m) => emit('pickValue', 'severity', cellValue('severity', data)!, m)"
            />
          </span>
        </template>
      </Column>
      <Column
        v-for="key in orderedKeys"
        :key="key"
        :column-key="key"
        :field="SORT_FIELD[key]"
        :sortable="key in SORT_FIELD"
        :class="colClass(key)"
      >
        <template #header>
          <span v-if="key === 'epss'">EPSS<span class="th-note">via Grype</span></span>
          <span v-else>{{ COL_HEADER[key] }}</span>
        </template>
        <!-- one wrapper for the whole chain: the actions belong at the cell's RIGHT EDGE, so
             they need a flex row spanning the cell rather than trailing the text -->
        <template #body="{ data }">
          <span class="cell-actionable">
          <span v-if="key === 'first_seen'" class="mono-cell sm nowrap" :title="data.first_seen_at ?? ''">{{ lastDataAt(data.first_seen_at ?? null) }}</span>
          <span v-else-if="key === 'last_scan'" class="mono-cell sm nowrap" :title="data.last_scan_at ?? ''">{{ lastDataAt(data.last_scan_at ?? null) }}</span>
          <EpssBar v-else-if="key === 'epss'" :v="data.epss" />
          <KevTag v-else-if="key === 'kev'" :on="data.kev === true" />
          <span v-else-if="key === 'package'" class="pkg" :title="data.package_name"
            ><em class="pkg-name">{{ data.package_name }}</em><i class="pkg-type">{{ data.ptype ?? 'unknown' }}</i></span
          >
          <span v-else-if="key === 'current'" class="mono-cell sm ver-cur">{{ data.installed_version ?? '-' }}</span>
          <template v-else-if="key === 'fixed'">
            <span v-if="data.fixed_version" class="mono-cell sm ver-fix">{{ data.fixed_version }}</span>
            <span v-else class="ver-none">no fix</span>
          </template>
          <span v-else-if="key === 'image'" class="mono-cell sm img-cell" :title="data.image_repo">{{ shortImage(data) }}</span>
          <span
            v-else-if="key === 'namespace'"
            class="mono-cell sm ns-cell"
            :title="Array.isArray(data.namespaces) ? data.namespaces.join(', ') : ''"
            >{{ nsLabel(data) }}</span
          >
          <span v-else-if="key === 'images'" class="mono-cell sm">{{ data.images_affected ?? '-' }}</span>
          <span v-else-if="key === 'scanner'" class="scanner-stack">
            <ScannerTag :name="data.scanner" />
            <DisagreementBadge v-if="data.disagree" />
          </span>
          <SlaCell v-else-if="key === 'sla'" :due-at="data.due_at" :overdue="data.overdue === true" :now-ms="slaNowMs" />
          <StateTag v-else-if="key === 'state'" :state="data.state" />
          <span v-else-if="key === 'assignee'" class="sm">{{ data.assignee ?? '-' }}</span>
          <!-- `image` names itself "Image (all tags)": the cell reads `repo:tag` but the
               filter is repo-only, so "+ nginx" also matches nginx:1.21.6 -->
          <ValueActions
            v-if="CELL_FILTER_FIELD[key] && cellValue(key, data)"
            class="val-act-reveal"
            :field="key === 'image' ? 'Image (all tags)' : COL_HEADER[key]"
            :value="cellValue(key, data)!"
            :shown="key === 'state' ? stateLabel(cellValue(key, data)!) : undefined"
            :active="cellActive(key, cellValue(key, data)!)"
            @pick="(m) => emit('pickValue', CELL_FILTER_FIELD[key]!, cellValue(key, data)!, m)"
          />
          </span>
        </template>
      </Column>
      <template #empty>
        <!-- "no findings" is an ANSWER; before a read comes back there is none. `loading` misses
             the window before the cluster resolves, when no request has started yet. -->
        <div class="empty-row">
          {{ props.loading || props.settled === false ? 'Loading findings…'
            : props.failed ? 'Findings could not be loaded.'
            : filtered ? 'No findings match these filters.'
            : 'No findings yet. The first committed scan populates this grid.' }}
        </div>
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
/* the table skin (.tbl-wrap / .tbl family / th-note / empty-row) lives in base.css —
   only this grid's own cells and chips are styled here */
/* the affordance carrier: the identifier reads as a link once the row is live (research: link
   cells > loud row hovers on dense tables) */
:deep(.cve-link) {
  transition: color 0.12s ease-out;
}
:deep(.tbl-hover tbody tr:hover .cve-link) {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  :deep(.cve-link) {
    transition: none;
  }
}
:deep(.img-cell) {
  display: inline-block;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
:deep(.ver-cur) {
  color: var(--soft);
}
:deep(.ver-fix) {
  color: var(--teal-text);
}
:deep(.ver-none) {
  color: var(--ver-none-fg);
  font-style: italic;
}
:deep(.pkg) {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
:deep(.pkg-name) {
  font-style: normal;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
:deep(.ns-cell) {
  display: inline-block;
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
:deep(.pkg-type) {
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  font-style: normal;
  color: var(--soft);
  background: var(--line2);
  padding: 2px 5px;
  border-radius: 4px;
  text-transform: lowercase;
}
:deep(.scanner-stack) {
  display: inline-flex;
  gap: 4px;
}
.empty-row {
  padding: 34px 12px; /* the primary grid breathes more than the skin default */
}
</style>

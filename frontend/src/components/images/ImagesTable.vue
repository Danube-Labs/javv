<script setup lang="ts">
/**
 * The running-images grid (M9c slice 3) — the SAME PrimeVue DataTable grammar as the M9b
 * findings grid (`.tbl` family, hover/link/cursor rulings), only the columns differ. The
 * inventory is one committed run, fully served — sorting is client-side over those rows
 * (emitted to the parent, which sorts + slices), never a server round-trip.
 */
import Column from 'primevue/column'
import DataTable, {
  type DataTableColumnReorderEvent,
  type DataTableSortEvent,
} from 'primevue/datatable'
import { computed, nextTick, ref, watch } from 'vue'
import type { RouteLocationRaw } from 'vue-router'

import CountDisagree from '@/components/chips/CountDisagree.vue'
import MixBar from '@/components/dashboards/MixBar.vue'
import ValueActions from '@/components/filters/ValueActions.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import RowLink from '@/components/ui/RowLink.vue'
import { activeMode, type Selections } from '@/filters/fields.config'
import { IMAGES_COLUMNS, type ImagesColumnKey } from '@/images/fields.config'
import type { FilterMode, Modes } from '@/stores/filters'
import type { ImageRow } from '@/stores/images'
import type { Severity } from '@/styles/tokens'
import { lastDataAt } from '@/system/freshness'

export type ImagesSortField = 'total' | 'replicas'

const props = withDefaults(
  defineProps<{
    rows: ImageRow[]
    sort: ImagesSortField | null
    order: 'asc' | 'desc'
    loading: boolean
    filtered: boolean
    /** keys from IMAGES_COLUMNS hidden via the Columns menu (only Image is fixed) */
    hidden?: ReadonlySet<string>
    /** IMAGES_COLUMNS keys in display order (hidden keys keep their slot) */
    colOrder?: readonly string[]
    /** header drag-reorder on; the parent owns + persists the order */
    reorderable?: boolean
    dense?: boolean
    /** active selections + modes, so a cell action shows which side it already sits on */
    selections?: Selections
    modes?: Modes
    /** where a row leads: its identifier renders as a real link, so the keyboard can open it */
    rowTo?: (row: ImageRow) => RouteLocationRaw
  }>(),
  {
    hidden: () => new Set<string>(),
    colOrder: () => IMAGES_COLUMNS.map(([key]) => key),
    reorderable: false,
    dense: true,
  },
)

const orderedKeys = computed(
  () => props.colOrder.filter((k) => !props.hidden.has(k)) as ImagesColumnKey[],
)

const SORT_FIELD: Partial<Record<ImagesColumnKey, ImagesSortField>> = {
  replicas: 'replicas',
  vulns: 'total',
}
// narrow data columns shrink to content; slack pools in the Image identity column
const FIT_COLS = new Set<ImagesColumnKey>(['tag', 'replicas', 'vulns', 'seen'])
const colClass = (key: ImagesColumnKey) =>
  [FIT_COLS.has(key) ? 'fit' : '', props.reorderable ? 'th-drag' : ''].join(' ').trim()

const emit = defineEmits<{
  sort: [field: ImagesSortField]
  rowClick: [row: ImageRow]
  /** raw PrimeVue rendered-column indexes — map with reorderFromDrag(pinnedLeft=1) */
  reorder: [dragIndex: number, dropIndex: number]
  /** a cell's value action (issue 349 §2): filter TO / OUT of this exact value */
  pickValue: [fieldKey: string, value: string, mode: FilterMode]
}>()

/** The mode this exact value is already filtered under, so the active side reads as pressed. */
const cellActive = (fieldKey: string, value: string): FilterMode | null =>
  activeMode(fieldKey, value, props.selections, props.modes)

function onSort(e: DataTableSortEvent) {
  if (typeof e.sortField === 'string') emit('sort', e.sortField as ImagesSortField)
}

const dt = ref<InstanceType<typeof DataTable> | null>(null)

// same PrimeVue parallel-order trap as the findings grid (see FindingsTable) — the
// parent-owned order is the truth; re-assert it on every change and drop
function syncPrimeOrder() {
  const inst = dt.value as unknown as { d_columnOrder?: string[] } | null
  if (inst) inst.d_columnOrder = ['image', ...orderedKeys.value]
}
watch(orderedKeys, () => void nextTick(syncPrimeOrder))

async function onColReorder(e: DataTableColumnReorderEvent) {
  emit('reorder', e.dragIndex, e.dropIndex)
  await nextTick()
  syncPrimeOrder()
}

const shortRepo = (r: ImageRow) => r.image_repo.split('/').at(-1) ?? r.image_repo
const registryOf = (r: ImageRow) =>
  r.image_repo.includes('/') ? r.image_repo.slice(0, r.image_repo.lastIndexOf('/')) : null
/** One scanner's mix from the server decoration (never merged); the doc's own buckets are
 * the fallback for its committing scanner; null = no committed scan by that scanner. */
function mixFor(r: ImageRow, sc: 'trivy' | 'grype'): Partial<Record<Severity, number>> | null {
  const c = r.severity_by_scanner?.[sc]
  if (c) {
    return {
      critical: c.crit ?? 0,
      high: c.high ?? 0,
      medium: c.med ?? 0,
      low: c.low ?? 0,
      negligible: c.negligible ?? 0,
      unknown: c.unknown ?? 0,
    }
  }
  if (!r.severity_by_scanner && r.scanners.includes(sc)) {
    return {
      critical: r.crit,
      high: r.high,
      medium: r.med,
      low: r.low,
      negligible: r.negligible,
      unknown: r.unknown,
    }
  }
  return null
}
/** Who has a committed scan of this digest: the server decoration when present, else the doc's
 * own scanner — the same precedence `mixFor` uses. */
const scannersFor = (r: ImageRow) =>
  r.severity_by_scanner ? Object.keys(r.severity_by_scanner) : r.scanners
const nsLabel = (r: ImageRow) =>
  r.namespaces.length <= 1 ? (r.namespaces[0] ?? '-') : `${r.namespaces[0]} +${r.namespaces.length - 1}`
const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="tbl-wrap">
    <DataTable
      ref="dt"
      :value="props.rows"
      lazy
      :sort-field="props.sort ?? undefined"
      :sort-order="props.order === 'desc' ? -1 : 1"
      :loading="props.loading"
      data-key="image_digest"
      :reorderable-columns="props.reorderable"
      :pt="{ table: { class: `tbl tbl-hover ${props.dense ? 'tbl-dense' : ''} ${props.reorderable ? 'tbl-reorder' : ''}` } }"
      @sort="onSort"
      @column-reorder="onColReorder"
      @row-click="(e) => emit('rowClick', e.data as ImageRow)"
    >
      <Column column-key="image" header="Image" :reorderable-column="false">
        <template #body="{ data }">
          <!-- `.img-id` stacks name over registry, so the actions sit BESIDE it, never inside
               it — a third child of that column pushed them onto their own line and grew the
               row (issue 349 §2) -->
          <div class="cell-actionable">
            <div class="img-id">
              <RowLink v-if="props.rowTo" :to="props.rowTo(data)" @open="emit('rowClick', data)">
                <span class="img-name img-link">{{ shortRepo(data) }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
              </RowLink>
              <span v-else class="img-name img-link">{{ shortRepo(data) }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
              <span v-if="registryOf(data)" class="mono-cell sm img-reg">{{ registryOf(data) }}</span>
            </div>
            <!-- the cell shortens the repo for display, so the action filters on the FULL
                 `image_repo` the row carries — never the shortened text -->
            <ValueActions
              v-if="data.image_repo"
              class="val-act-reveal"
              field="Image"
              :value="data.image_repo"
              :active="cellActive('repo', data.image_repo)"
              @pick="(m) => emit('pickValue', 'repo', data.image_repo, m)"
            />
          </div>
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
          <span v-if="key === 'tag'">Tag</span>
          <span v-else-if="key === 'namespace'">Namespace</span>
          <span v-else-if="key === 'replicas'">Replicas<span class="th-note">at last sweep</span></span>
          <span v-else-if="key === 'vulns'">Vulns<span class="th-note">Trivy / Grype</span></span>
          <span v-else-if="key === 'mixTrivy'">Severity mix<span class="th-note">trivy</span></span>
          <span v-else-if="key === 'mixGrype'">Severity mix<span class="th-note">grype</span></span>
          <span v-else-if="key === 'seen'">Last seen</span>
        </template>
        <template #body="{ data }">
          <span v-if="key === 'tag'" class="cell-actionable">
            <span v-if="data.tag" class="mono-cell sm">{{ data.tag }}</span>
            <span v-else class="muted-dash" title="Pinned by digest: the pod names no tag.">-</span>
            <ValueActions
              v-if="data.tag"
              class="val-act-reveal"
              field="Tag"
              :value="data.tag"
              :active="cellActive('tag', data.tag)"
              @pick="(m) => emit('pickValue', 'tag', data.tag, m)"
            />
          </span>
          <span v-else-if="key === 'namespace'" class="cell-actionable">
            <span class="mono-cell sm" :title="data.namespaces.join(', ')">{{ nsLabel(data) }}</span>
            <!-- only a single-namespace row has one true value to filter on; the mix and
                 scanner columns have none at all, so they carry no action (issue 349 §2) -->
            <ValueActions
              v-if="data.namespaces.length === 1"
              class="val-act-reveal"
              field="Namespace"
              :value="data.namespaces[0]!"
              :active="cellActive('namespace', data.namespaces[0]!)"
              @pick="(m) => emit('pickValue', 'namespace', data.namespaces[0]!, m)"
            />
          </span>
          <span v-else-if="key === 'replicas'" class="mono-cell">{{ fmt(data.replicas ?? 0) }}</span>
          <CountDisagree
            v-else-if="key === 'vulns'"
            :trivy="data.trivy_count"
            :grype="data.grype_count"
            :total="data.total"
            :scanners="scannersFor(data)"
          />
          <template v-else-if="key === 'mixTrivy'">
            <MixBar v-if="mixFor(data, 'trivy')" :counts="mixFor(data, 'trivy')!" numbers attribution="trivy" class="mix-sized" />
            <span v-else class="muted-dash" title="No committed trivy scan of this digest">-</span>
          </template>
          <template v-else-if="key === 'mixGrype'">
            <MixBar v-if="mixFor(data, 'grype')" :counts="mixFor(data, 'grype')!" numbers attribution="grype" class="mix-sized" />
            <span v-else class="muted-dash" title="No committed grype scan of this digest">-</span>
          </template>
          <span v-else-if="key === 'seen'" class="mono-cell sm nowrap">{{ lastDataAt(data['@timestamp']) }}</span>
        </template>
      </Column>
      <template #empty>
        <div class="empty-row">
          {{ filtered ? 'No images match these filters.' : 'No running images in the committed inventory.' }}
        </div>
      </template>
    </DataTable>
  </div>
</template>

<style scoped>
/* the table skin (.tbl-wrap / .tbl family / th-note / empty-row) lives in base.css —
   only this grid's own cells are styled here */

.img-id {
  display: flex;
  flex-direction: column;
}
.img-name {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  color: var(--ink);
}
.img-reg {
  color: var(--soft);
}
/* the affordance carrier — identifier takes the link treatment on row hover (ruled) */
.img-link {
  transition: color var(--dur-quick);
}
:deep(.tbl-hover tbody tr:hover) .img-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.cell-go {
  color: var(--dash-muted);
  margin-left: 4px;
  transition: color var(--dur-quick);
}
:deep(.tbl-hover tbody tr:hover) .cell-go {
  color: var(--coral-text);
}
.mix-sized {
  min-width: 140px;
}
@media (prefers-reduced-motion: reduce) {
  :deep(.tbl-hover tbody tr),
  .img-link,
  .cell-go {
    transition: none;
  }
}
</style>

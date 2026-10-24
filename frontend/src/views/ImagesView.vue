<script setup lang="ts">
/**
 * Running images — the committed-inventory surface (M9c slice 3; SCREENS §7, prototype
 * screens-images.jsx). The M9a filter module drives the rail + bar (imported, never re-built;
 * an images-scoped store instance keeps shareable URLs); the grid is the M9b table grammar
 * with image columns. The inventory is ONE committed run, fully served — filtering, facet
 * counts (image counts), sorting, and paging are pure client operations over those served
 * rows (unit-tested in imageFilters.ts); every underlying number is still the server's.
 * Fully time-travelable: the global T rides `as_of` into the same primitives as the M8b
 * reader; no committed inventory at T = "unknown", never an empty cluster. Image naming
 * composes `image_repo` + `tag` — no combined image_ref field exists on the docs.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import FacetRail from '@/components/filters/FacetRail.vue'
import FilterBar from '@/components/filters/FilterBar.vue'
import SevChip from '@/components/chips/SevChip.vue'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import ColumnsMenu from '@/components/findings/ColumnsMenu.vue'
import GridPager from '@/components/findings/GridPager.vue'
import ImagesTable, { type ImagesSortField } from '@/components/images/ImagesTable.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiRoleNote from '@/components/ui/UiRoleNote.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useApi } from '@/composables/useApi'
import { IMAGES_COLUMNS, IMAGES_FIELDS } from '@/images/fields.config'
import { reorderFromDrag, restoreHidden, restoreOrder } from '@/system/columnOrder'
import { filterImages, imagesCsv, imagesFacets } from '@/images/imageFilters'
import { logger } from '@/lib/logger'
import { NO_EXPORT_NOTE, useAuthStore } from '@/stores/auth'
import { makeFiltersStore } from '@/stores/filters'
import { useClusterStore } from '@/stores/cluster'
import { useImagesStore, type ImageRow } from '@/stores/images'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'
import { lastDataAt } from '@/system/freshness'
import { foreignQuery } from '@/system/globalUrl'

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()
const images = useImagesStore()
const canExport = computed(() => useAuthStore().hasCapability('can_export'))
const filters = makeFiltersStore('imageFilters', IMAGES_FIELDS)()
const { withGlobals } = useApi()

filters.fromQuery(route.query)
const OWN_KEYS = IMAGES_FIELDS.map((f) => f.key)
watch(
  () => filters.toQuery(),
  // rewrite only this screen's own keys — globals and foreign params survive (audit 343)
  (q) => void router.replace({ query: { ...foreignQuery(route.query, OWN_KEYS), ...q } }),
)

watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  ([id]) => {
    if (id) void images.load(withGlobals({ cluster_id: id }))
  },
  { immediate: true },
)

/* ---- pure client pipeline over the served run: filter → facets → sort → slice ---- */
const filtered = computed(() => filterImages(images.images, filters.selections, filters.modes))
const facets = computed(() => imagesFacets(images.images))

const sort = ref<ImagesSortField | null>(null)
const order = ref<'asc' | 'desc'>('desc')
const size = ref(25)
const page = ref(0)
watch([filtered, size], () => (page.value = 0))

const sorted = computed(() => {
  if (!sort.value) return filtered.value
  const key = sort.value
  const dir = order.value === 'desc' ? -1 : 1
  return [...filtered.value].sort((a, b) => ((a[key] ?? 0) as number) - ((b[key] ?? 0) as number) > 0 ? dir : -dir)
})
const pageRows = computed(() => sorted.value.slice(page.value * size.value, (page.value + 1) * size.value))

function onSort(field: ImagesSortField) {
  if (sort.value === field) {
    order.value = order.value === 'desc' ? 'asc' : 'desc'
  } else {
    sort.value = field
    order.value = 'desc'
  }
}

/* columns + density — the findings pattern, images-scoped keys */
const COLS_KEY = 'javv.images.hidden_cols'
const DENSE_KEY = 'javv.images.dense'
const hiddenCols = ref<Set<string>>(
  restoreHidden(localStorage.getItem(COLS_KEY), IMAGES_COLUMNS.map(([key]) => key), []),
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

/* column order (task 92) — the findings pattern, images-scoped key */
const ORDER_KEY = 'javv.images.col_order'
const colOrder = ref<string[]>(
  restoreOrder(localStorage.getItem(ORDER_KEY), IMAGES_COLUMNS.map(([key]) => key)),
)
const orderedCols = computed(() =>
  colOrder.value.map((key) => IMAGES_COLUMNS.find(([k]) => k === key)!),
)
function setColOrder(next: string[]) {
  colOrder.value = next
  localStorage.setItem(ORDER_KEY, JSON.stringify(next))
}
function onHeaderReorder(dragIndex: number, dropIndex: number) {
  // 1 = the pinned Image identity column the PrimeVue indexes count past
  const next = reorderFromDrag(colOrder.value, hiddenCols.value, dragIndex, dropIndex, 1)
  if (next) setColOrder(next)
}

function imageRoute(row: ImageRow) {
  return {
    name: 'image-detail',
    params: { digest: row.image_digest },
    query: { repo: row.image_repo, tag: row.tag },
  }
}
function openImage(row: ImageRow) {
  void router.push(imageRoute(row))
}

/** The list export — inventory rows already served; findings exports stay M6/M7's. */
function exportCsv() {
  const csv = imagesCsv(sorted.value)
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  const a = document.createElement('a')
  a.href = url
  a.download = `javv-images-${clusterStore.selectedId ?? 'cluster'}.csv`
  a.click()
  URL.revokeObjectURL(url)
  logger.info('images_csv_exported', { rows: sorted.value.length })
  toast.success(`Exported ${sorted.value.length.toLocaleString('en-US')} image rows to CSV.`)
}

const totalReplicas = computed(() => images.images.reduce((n, r) => n + (r.replicas ?? 0), 0))
const inventoryAt = computed(() =>
  images.inventory?.completed_at ? lastDataAt(images.inventory.completed_at) : null,
)
const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Running images</h1>
        <template v-if="images.inventory">
          <p class="head-stat">
            {{ fmt(filtered.length) }}<span class="head-unit">
              <template v-if="filtered.length !== images.images.length">of {{ fmt(images.images.length) }} </template>image{{ filtered.length === 1 ? '' : 's' }}</span>
            · {{ fmt(totalReplicas) }}<span class="head-unit"> replicas</span>
          </p>
          <p class="head-note">
            <template v-if="inventoryAt">inventory as of <span class="mono-cell">{{ inventoryAt }}</span> · </template>digest-deduped
          </p>
        </template>
        <p v-else class="head-note">the latest committed inventory, per digest</p>
      </div>
      <IngestLens v-if="clusterStore.selectedId" :cluster-id="clusterStore.selectedId" />
    </div>

    <div v-if="images.loading || !images.settled" aria-busy="true" aria-label="Loading images">
      <UiSkeleton :height="320" />
    </div>

    <p v-else-if="images.failed" class="load-error" role="alert">
      Inventory unavailable. Check the backend connection.
    </p>

    <div v-else-if="images.unknown" class="first-run">
      <h2>No inventory committed{{ timeTravel.isNow ? ' yet' : ' at this point in time' }}</h2>
      <p>
        Images appear once a scanner cycle completes and certifies its inventory.
        <template v-if="!timeTravel.isNow">This T predates the first committed run.</template>
      </p>
    </div>

    <div v-else class="findings-layout">
      <div class="rail-col">
        <div class="facet-search">
          <AppIcon name="search" :size="14" />
          <input
            :value="filters.selections.q?.[0] ?? ''"
            placeholder="image, registry, namespace…"
            aria-label="Search images (contains match)"
            @keydown.enter="filters.setText('q', ($event.target as HTMLInputElement).value)"
          />
        </div>
        <FacetRail
          :fields="IMAGES_FIELDS"
          :selections="filters.selections"
          :facets="facets"
          :modes="filters.modes"
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
            :fields="IMAGES_FIELDS"
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
            :disabled="filtered.length === 0 || !canExport"
            :aria-describedby="canExport ? undefined : 'no-export-note'"
            @click="exportCsv"
          >
            <AppIcon name="download" :size="14" /> Export CSV
          </UiButton>
          <UiRoleNote v-if="!canExport" id="no-export-note">{{ NO_EXPORT_NOTE }}</UiRoleNote>
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
<div class="tbl-card">
        <ImagesTable
          :rows="pageRows"
          :sort="sort"
          :order="order"
          :loading="images.loading"
          :filtered="filters.hasFilters"
          :hidden="hiddenCols"
          :col-order="colOrder"
          :selections="filters.selections"
          :modes="filters.modes"
          reorderable
          :dense="dense"
          :row-to="imageRoute"
          @pick-value="filters.pickValue"
          @sort="onSort"
          @row-click="openImage"
          @reorder="onHeaderReorder"
        />
        <GridPager
          :total="filtered.length"
          :page="page"
          :size="size"
          :shown="pageRows.length"
          :has-prev="page > 0"
          :has-next="(page + 1) * size < filtered.length"
          @prev="page -= 1"
          @next="page += 1"
          @update:size="(s: number) => (size = s)"
        />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* head/layout/toolbar scaffolding lives in base.css (shared data-screen grammar) */
.first-run {
  padding: 48px 0;
  text-align: center;
  color: var(--soft);
}
.first-run h2 {
  color: var(--ink);
  margin: 0 0 6px;
}

</style>

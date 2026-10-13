<script setup lang="ts">
/**
 * The image-detail findings block (issue 384 split — extracted from ImageDetailView, no
 * behavior change): cursor-stack paging local to this screen, one query family — the same
 * server reads the Findings screen uses (`image_digest` + `scanner` scoped), so the two
 * screens can never disagree; `as_of` rides every query via withGlobals.
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import type { SearchFindingsApiV1FindingsGetData } from '@/api/generated'
import { searchFindingsApiV1FindingsGet } from '@/api/generated'
import FindingsTable from '@/components/findings/FindingsTable.vue'
import GridPager from '@/components/findings/GridPager.vue'
import { useApi } from '@/composables/useApi'
import { useCursorPager } from '@/composables/useCursorPager'
import type { SortField, SortOrder } from '@/findings/buildFindingsQuery'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import type { FindingRow } from '@/stores/findings'
import { useTimeTravelStore } from '@/stores/timeTravel'

/* image/affected-images are this screen's own context; scanner is fixed by the lens */
const HIDDEN_COLUMNS: ReadonlySet<string> = new Set(['image', 'images', 'scanner'])

const props = defineProps<{ digest: string; scanner: 'trivy' | 'grype' }>()

const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const { withGlobals } = useApi()

const rows = ref<FindingRow[]>([])
const total = ref(0)
const loading = ref(false)
const failed = ref(false)
const sort = ref<SortField>('severity_rank')
const order = ref<SortOrder>('desc')
const pager = useCursorPager()
const { page, size, hasPrev, hasNext } = pager

const baseQuery = computed(() =>
  clusterStore.selectedId
    ? withGlobals({
        cluster_id: clusterStore.selectedId,
        image_digest: props.digest,
        scanner: props.scanner,
      })
    : null,
)

async function loadRows() {
  if (!baseQuery.value) return
  loading.value = true
  const live = !baseQuery.value.as_of // a past-T page holds no search on the server
  const { data, response } = await searchFindingsApiV1FindingsGet({
    query: {
      ...baseQuery.value,
      sort: sort.value,
      order: order.value,
      size: size.value,
      keep_open: true, // the last page keeps its search, so Prev from it works
      ...(pager.cursor.value ? { cursor: pager.cursor.value } : {}),
    } as SearchFindingsApiV1FindingsGetData['query'],
  })
  loading.value = false
  if (response?.ok && data) {
    const body = data as { data: FindingRow[]; total: { value: number }; next_cursor: string | null }
    rows.value = body.data
    total.value = body.total.value
    pager.landed(body.next_cursor, live)
    failed.value = false
  } else {
    failed.value = true
    logger.warn('image_detail_rows_failed', { status: response?.status })
  }
}

watch(
  [baseQuery, sort, order, size],
  () => {
    pager.reset()
    void loadRows()
  },
  { immediate: true },
)

function onSort(field: SortField) {
  if (sort.value === field) {
    order.value = order.value === 'desc' ? 'asc' : 'desc'
  } else {
    sort.value = field
    order.value = 'desc'
  }
}
// the panel's walk is its own: leaving the image closes it, whatever comes next
onUnmounted(() => pager.reset())

function goNext() {
  if (pager.next()) void loadRows()
}
function goPrev() {
  if (pager.prev()) void loadRows()
}

function findingRoute(row: FindingRow) {
  return {
    name: 'finding',
    params: { cveId: row.cve_id },
    query: { digest: props.digest, scanner: row.scanner, package: row.package_name ?? '' },
  }
}
function openFinding(row: FindingRow) {
  logger.debug('image_finding_row_clicked', { finding_key: row.finding_key })
  void router.push(findingRoute(row))
}
</script>

<template>
  <p v-if="failed" class="load-error" role="alert">
    Image findings unavailable. Check the backend connection.
  </p>

  <div v-else-if="!loading && rows.length === 0" class="card first-run">
    <h2>No findings from {{ scanner }}</h2>
    <p>
      {{ timeTravel.isNow
        ? `No committed ${scanner} findings for this digest: a clean scan, or not scanned by ${scanner} yet.`
        : `As scanned at this T: no committed ${scanner} findings for this digest: clean then, or not yet scanned.` }}
    </p>
  </div>
  <div v-else class="tbl-card">
    <FindingsTable
      :rows="rows"
      :sort="sort"
      :order="order"
      :loading="loading"
      :hidden="HIDDEN_COLUMNS"
      :row-to="findingRoute"
      @sort="onSort"
      @row-click="openFinding"
    />
    <GridPager
      :total="total"
      :page="page"
      :size="size"
      :shown="rows.length"
      :has-prev="hasPrev"
      :has-next="hasNext"
      @prev="goPrev"
      @next="goNext"
      @update:size="pager.setSize"
    />
  </div>
</template>

<style scoped>
.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
.first-run {
  padding: 48px 0;
  text-align: center;
  color: var(--soft);
}
.first-run h2 {
  color: var(--ink);
  margin: 0 0 6px;
}
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
}
</style>

<script setup lang="ts">
/**
 * Saved views (SCREENS §6, M9f slice 4; backend M8e/C-6): the card grid of fleet-global
 * presets. Every card shows the lens summary + a LIVE server count under the selected cluster
 * (never counted client-side); applying a card lands on /findings with the identical query
 * params (the §6 deep-link round-trip) plus the captured workbench — columns/density through
 * the same localStorage keys the Columns menu owns, sort through the grid store, the relative
 * window through the time store. Mutations are owner-or-admin; everyone else sees no ✕.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import {
  deleteViewApiV1ViewsViewIdDelete,
  facetFindingsApiV1FindingsFacetsGet,
  listViewsApiV1ViewsGet,
} from '@/api/generated'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { usePagedSlice } from '@/composables/usePagedSlice'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { FINDINGS_COLUMNS } from '@/findings/columns'
import {
  facetsTotal,
  FINDINGS_COLS_KEY,
  FINDINGS_DENSE_KEY,
  FINDINGS_ORDER_KEY,
  presetCountQuery,
  presetSummary,
  presetToRouteQuery,
  type ViewPreset,
  type ViewWorkbench,
} from '@/findings/savedViews'
import { readFailureCopy } from '@/findings/failureCopy'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useFindingsStore } from '@/stores/findings'
import type { SortField, SortOrder } from '@/findings/buildFindingsQuery'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'

interface ViewDoc {
  view_id: string
  name: string
  description: string
  owner: string
  preset: ViewPreset
  workbench?: ViewWorkbench | null
  updated_at: string
}

const auth = useAuthStore()
const clusterStore = useClusterStore()
const grid = useFindingsStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()
const router = useRouter()

const views = ref<ViewDoc[]>([])
const loaded = ref(false)
const failed = ref(false)
const failedStatus = ref<number | null>(null)
/** Display paging over the fetched list (usePagedSlice — the bounded-board model). */
const pager = usePagedSlice(() => views.value, 10)
/** view_id → live count; null = count degraded (em-dash), absent = loading */
const counts = ref<Record<string, number | null>>({})

async function load() {
  const { response, data } = await listViewsApiV1ViewsGet()
  failed.value = !response?.ok || !data
  failedStatus.value = response?.status ?? null
  views.value = failed.value ? [] : ((data as { views: ViewDoc[] }).views ?? [])
  loaded.value = true
  void loadCounts()
}

/** SCREENS §6: per-card counts come from /findings/facets — a size-0 server agg, no PIT
 * (the /findings path leaks a cursor per card and 429s past the concurrency cap). Small
 * batches so a long card list never floods the backend. */
async function loadCounts() {
  const cid = clusterStore.selectedId
  if (!cid) return
  const asOf = (timeTravel.asOfParams as { as_of?: string }).as_of
  const BATCH = 6
  for (let i = 0; i < views.value.length; i += BATCH) {
    await Promise.all(
      views.value.slice(i, i + BATCH).map(async (v) => {
        try {
          const { response, data } = await facetFindingsApiV1FindingsFacetsGet({
            query: presetCountQuery(v.preset, cid, asOf) as never,
          })
          counts.value[v.view_id] = response?.ok ? facetsTotal(data) : null
        } catch {
          counts.value[v.view_id] = null
        }
      }),
    )
  }
}

onMounted(() => void load())
watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  () => {
    counts.value = {}
    void loadCounts()
  },
)

const canAdmin = computed(() => auth.hasCapability('can_manage_settings'))
function mayDelete(v: ViewDoc): boolean {
  return canAdmin.value || v.owner === auth.user?.username
}

function apply(v: ViewDoc) {
  const wb = v.workbench
  if (wb?.columns && wb.columns.length > 0) {
    // the same keys the Columns menu persists — the findings table reads them on mount
    const all = FINDINGS_COLUMNS.map(([key]) => key)
    const visible = new Set(wb.columns)
    localStorage.setItem(FINDINGS_COLS_KEY, JSON.stringify(all.filter((k) => !visible.has(k))))
    localStorage.setItem(FINDINGS_ORDER_KEY, JSON.stringify(wb.columns))
  }
  if (wb?.dense !== null && wb?.dense !== undefined) {
    localStorage.setItem(FINDINGS_DENSE_KEY, String(wb.dense))
  }
  if (wb?.sort) grid.setSort(wb.sort as SortField)
  if (wb?.order) grid.order = wb.order as SortOrder
  if (wb?.window_days) {
    const days = wb.window_days
    timeTravel.setWindow(days, days >= 1 ? `Last ${days} day${days === 1 ? '' : 's'}` : 'Custom window')
  }
  logger.debug('view_applied', { view_id: v.view_id })
  void router.push({ path: '/findings', query: presetToRouteQuery(FINDINGS_FIELDS, v.preset) })
}

async function remove(v: ViewDoc) {
  const { response } = await deleteViewApiV1ViewsViewIdDelete({ path: { view_id: v.view_id } })
  if (response?.ok || response?.status === 404) {
    views.value = views.value.filter((x) => x.view_id !== v.view_id)
    toast.success(`View “${v.name}” deleted`)
  } else {
    logger.warn('view_delete_failed', { view_id: v.view_id, status: response?.status })
    toast.error('Deleting the view failed. Try again.')
  }
}

function summary(v: ViewDoc): string {
  return presetSummary(FINDINGS_FIELDS, v.preset)
}
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Saved views</h1>
        <p class="head-stat">
          <!-- a count not yet read, or refused, is unknown, not zero (issue 833, F5) -->
          <template v-if="loaded && !failed">{{ views.length }}</template
          ><span v-else class="muted-dash">-</span><span class="head-unit"> views</span>
        </p>
        <p class="head-note">fleet-global lenses · counts are live for the selected cluster</p>
      </div>
    </div>

    <p v-if="failed" class="load-error" role="alert">
      {{ readFailureCopy(failedStatus, 'Saved views unavailable. Check the backend, then reload.') }}
    </p>

    <EmptyState
      v-else-if="loaded && views.length === 0"
      icon="layers"
      title="No saved views yet"
      hint="Set up Findings the way you want it (filters, columns, density, time window), then use “Save view” to keep it here for everyone."
    >
      <UiButton variant="primary" @click="router.push('/findings')">Go to Findings</UiButton>
    </EmptyState>

    <div v-else class="views-grid">
      <article v-for="v in pager.shown.value" :key="v.view_id" class="view-card">
        <div class="vc-head">
          <h2>{{ v.name }}</h2>
          <button
            v-if="mayDelete(v)"
            type="button"
            class="vc-x"
            :aria-label="`Delete ${v.name}`"
            @click="remove(v)"
          >
            ×
          </button>
        </div>
        <p v-if="v.description" class="vc-desc">{{ v.description }}</p>
        <p class="vc-summary">{{ summary(v) }}</p>
        <div class="vc-foot">
          <span class="vc-count">
            <template v-if="counts[v.view_id] === undefined">…</template>
            <span v-else-if="counts[v.view_id] === null" class="muted-dash">-</span>
            <template v-else>{{ counts[v.view_id]!.toLocaleString('en-US') }} findings</template>
          </span>
          <span class="vc-owner mono">{{ v.owner }}</span>
          <UiButton variant="mini" @click="apply(v)">
            <AppIcon name="chevron" :size="12" />Open in Findings
          </UiButton>
        </div>
      </article>
    </div>

    <!-- the pager lives in a card like every other GridPager (the 2026-07-13 in-card rule) —
         here the "card" is a slim footer bar under the grid, since cards ARE the rows -->
    <div v-if="loaded && !failed && views.length > 0" class="views-pager">
      <GridPager
        :total="views.length"
        :page="pager.page.value"
        :size="pager.size.value"
        :shown="pager.shown.value.length"
        :has-prev="pager.page.value > 0"
        :has-next="pager.hasNext.value"
        @prev="pager.page.value -= 1"
        @next="pager.page.value += 1"
        @update:size="pager.setSize"
      />
    </div>
  </div>
</template>

<style scoped>
.views-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
  margin-top: 16px;
}
.views-pager {
  margin-top: 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
/* the card IS the container — the pager's own in-table top rule would double the border */
.views-pager :deep(.pager) {
  border-top: 0;
}
.view-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.view-card:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.vc-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.vc-head h2 {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
}
.vc-x {
  border: 0;
  background: transparent;
  color: var(--soft);
  font-size: var(--text-body);
  line-height: 1;
  padding: 2px 6px;
  border-radius: var(--r-sm);
  cursor: default;
}
.vc-x:hover {
  background: var(--fpill-x-hover-bg);
  color: var(--coral-text);
}
.vc-desc {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--ink);
}
.vc-summary {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--soft);
  font-style: italic;
}
.vc-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: auto;
  padding-top: 6px;
}
.vc-count {
  font-weight: 600;
  font-size: var(--text-sm);
}
.vc-owner {
  flex: 1;
  font-size: var(--text-facet-label);
  color: var(--soft);
}
</style>

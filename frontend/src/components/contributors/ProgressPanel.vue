<script setup lang="ts">
/**
 * Triage progress (M9d slice 3 enhancement, operator ask): per-severity "X of Y triaged" —
 * how much work is done vs left. Both numbers are SERVER facet aggregations (two
 * `/findings/facets` reads: totals; the same read filtered to TRIAGED_STATES) — counts are
 * per-scanner finding rows, the same unit as Overview's KPI band, never a client CVE-merge.
 * State-at-T, NOT window-scoped — the sub says so, so it can't be conflated with the board's
 * trend window. Rows click through to what's LEFT (findings, severity + open/stale). On a
 * dashboard the panel's filters go in both reads and in the links.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { facetFindingsApiV1FindingsFacetsGet } from '@/api/generated'
import type { FacetFindingsApiV1FindingsFacetsGetData, ViewPreset } from '@/api/generated'
import SevChip from '@/components/chips/SevChip.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import {
  fillTransform,
  progressRows,
  TRIAGED_STATES,
  UNTRIAGED_STATES,
  type FacetBucket,
} from '@/contributors/viewModel'
import { panelFindingsQuery, panelQuery } from '@/dashboards/panelFilters'
import { logger } from '@/lib/logger'
import { SEVERITIES } from '@/styles/tokens'

const props = defineProps<{
  /** the screen's global query (cluster_id + as_of) — the panel rewinds with the app */
  query: Record<string, unknown> | null
  /** a dashboard panel's own filters (issue 999); never a state filter, the panel splits by it */
  filters?: ViewPreset | null
}>()
const router = useRouter()

const totals = ref<FacetBucket[]>([])
const done = ref<FacetBucket[]>([])
const failed = ref(false)
const settled = ref(false)

watch(
  () => [props.query, props.filters] as const,
  async ([q], prev) => {
    if (!q) return
    const old = prev?.[0]
    if (old && old.cluster_id !== q.cluster_id) {
      settled.value = false
      totals.value = []
      done.value = []
    }
    const base = panelQuery(
      { cluster_id: String(q.cluster_id), ...(q.as_of ? { as_of: String(q.as_of) } : {}) },
      props.filters,
    )
    const [all, triaged] = await Promise.all([
      facetFindingsApiV1FindingsFacetsGet({
        query: base as FacetFindingsApiV1FindingsFacetsGetData['query'],
      }),
      facetFindingsApiV1FindingsFacetsGet({
        query: { ...base, state: [...TRIAGED_STATES] } as FacetFindingsApiV1FindingsFacetsGetData['query'],
      }),
    ])
    failed.value = !all.response?.ok || !triaged.response?.ok || !all.data || !triaged.data
    if (failed.value) {
      logger.warn('triage_progress_failed', {
        totals: all.response?.status,
        done: triaged.response?.status,
      })
    } else {
      type Facets = { facets: Record<string, FacetBucket[]> }
      totals.value = (all.data as unknown as Facets).facets?.severity ?? []
      done.value = (triaged.data as unknown as Facets).facets?.severity ?? []
    }
    settled.value = true
  },
  { immediate: true, deep: true },
)

const rows = computed(() => progressRows(totals.value, done.value, SEVERITIES))
const overall = computed(() => {
  const t = rows.value.reduce((n, r) => n + r.total, 0)
  const d = rows.value.reduce((n, r) => n + r.done, 0)
  return { done: d, total: t }
})
const fmt = (n: number) => n.toLocaleString('en-US')
const pct = (r: { done: number; total: number }) =>
  r.total === 0 ? 0 : Math.round((r.done / r.total) * 100)

/** click a row → the work LEFT: findings filtered to the severity + untriaged states */
function openLeft(severity: string) {
  logger.debug('triage_progress_clicked', { severity })
  void router.push({
    name: 'findings',
    query: panelFindingsQuery(props.filters, { severity, state: UNTRIAGED_STATES.join(',') }),
  })
}
</script>

<template>
  <div v-if="!settled" class="prog-skel" aria-busy="true" aria-label="Loading triage progress">
    <UiSkeleton v-for="i in 3" :key="i" :height="22" radius="sm" />
  </div>
  <p v-else-if="failed" class="load-error" role="alert">
    Triage progress unavailable. Check the backend connection.
  </p>
  <p v-else-if="rows.length === 0" class="prog-empty" role="status">
    No findings in the store yet. Progress appears after the first committed scan.
  </p>
  <div v-else class="prog">
    <button
      v-for="r in rows"
      :key="r.severity"
      class="prog-row"
      :title="`Open the ${fmt(r.total - r.done)} untriaged ${r.severity} findings`"
      @click="openLeft(r.severity)"
    >
      <span class="prog-sev"><SevChip :level="r.severity" /></span>
      <span class="prog-track" aria-hidden="true">
        <i class="prog-fill" :style="{ transform: fillTransform(pct(r)) }" />
      </span>
      <span class="prog-nums mono-cell sm"
        ><b>{{ fmt(r.done) }}</b> / {{ fmt(r.total) }}</span
      >
      <span class="prog-pct mono-cell sm">{{ pct(r) }}%</span>
    </button>
    <p class="prog-total">
      <b>{{ fmt(overall.done) }}</b> of <b>{{ fmt(overall.total) }}</b> findings triaged ·
      {{ fmt(overall.total - overall.done) }} left
    </p>
  </div>
</template>

<style scoped>
.prog {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
/* one row = chip · track · numbers; the whole row is the click target (feedback mandatory) */
.prog-row {
  display: grid;
  grid-template-columns: 92px 1fr auto 44px;
  align-items: center;
  gap: 10px;
  padding: 6px 6px;
  border: none;
  background: none;
  font: inherit;
  text-align: left;
  border-radius: var(--r-sm);
  transition: background var(--dur-quick);
}
.prog-row:hover {
  background: var(--control-hover-bg);
}
.prog-row:active {
  background: var(--control-active-bg);
}
.prog-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: -2px;
}
.prog-sev {
  display: flex;
}
/* done-fraction meter: ONE hue for "done" everywhere (progress semantics — severity already
   speaks through the chip); track = the quiet hairline family */
.prog-track {
  display: block;
  height: 7px;
  border-radius: 4px;
  background: var(--meter-track);
  overflow: hidden;
}
/* full width, slid left by `fillTransform` — a transform composites, a width relayouts the row
   on every frame of the transition (issue 484) */
.prog-fill {
  display: block;
  width: 100%;
  height: 100%;
  background: var(--state-resolved-solid);
  border-radius: 4px;
  transition: transform var(--dur-quick);
}
@media (prefers-reduced-motion: reduce) {
  .prog-fill {
    transition: none;
  }
}
.prog-nums {
  color: var(--soft);
  white-space: nowrap;
}
.prog-nums b {
  color: var(--ink);
  font-weight: 700;
}
.prog-pct {
  color: var(--ink);
  font-weight: 700;
  text-align: right;
}
.prog-total {
  margin: 8px 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--line2);
  font-size: var(--text-sm);
  color: var(--soft);
}
.prog-total b {
  color: var(--ink);
  font-family: var(--font-mono);
  font-weight: 700;
}
.prog-empty {
  margin: 0;
  padding: var(--space-4) 0;
  color: var(--soft);
  font-size: var(--text-body);
}
.load-error {
  margin: 0;
}
.prog-skel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 6px 0;
}
</style>

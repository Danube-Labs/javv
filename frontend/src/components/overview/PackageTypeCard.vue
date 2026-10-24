<script setup lang="ts">
/**
 * The Overview "Package type" card (B-1: the v4 donut, fed by the M8d `ptype` facet), out of
 * OverviewView so a dashboard can show it: the share of findings per package type under the
 * scanner lens, each slice and legend row a click-through to the ptype-filtered grid. Overview
 * passes its facets read; on a dashboard the card reads its own (useFindingsFacets).
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { buildPtypeDonutOption } from '@/charts/buildPtypeDonutOption'
import EChart from '@/components/charts/EChart.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useFindingsFacets, type Facets, type FacetsQuery } from '@/composables/useFindingsFacets'
import { countOf, fmt, type ScannerLens } from '@/lib/scannerLens'
import { CHART_PTYPE_RAMP } from '@/styles/tokens'

const props = defineProps<{
  scanner: ScannerLens
  /** the screen's facets read; without it the card reads its own for `query` */
  facets?: Facets
  query?: FacetsQuery | null
}>()

const router = useRouter()
const { facets, settled, failed } = useFindingsFacets(
  () => props.facets,
  () => props.query,
)

/** ptype buckets minus a lone `unknown` (pre-M8d rows heal on the next sweep, D30). */
const ptypeBuckets = computed(() =>
  (facets.value.ptype ?? [])
    .map((b) => ({ key: b.key, count: countOf(b, props.scanner) }))
    .filter((b) => b.key !== 'unknown' && b.count > 0),
)
const donutOption = computed(() => buildPtypeDonutOption(ptypeBuckets.value))

function goFindings(ptype: string) {
  void router.push({ path: '/findings', query: { ptype } })
}
function onDonutClick(e: { name?: string }) {
  if (e?.name) goFindings(e.name)
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h2>Package type</h2>
        <p class="card-sub">share of findings</p>
      </div>
    </div>
    <div class="card-body">
      <UiSkeleton v-if="!settled" :height="188" radius="sm" label="Loading package types" />
      <p v-else-if="failed" class="empty-row" role="alert">Package-type counts unavailable.</p>
      <template v-else-if="ptypeBuckets.length">
        <EChart :option="donutOption" :height="188" @click="onDonutClick" />
        <div class="donut-legend">
          <button
            v-for="(b, i) in ptypeBuckets.slice(0, 6)"
            :key="b.key"
            class="donut-row"
            :title="`Open ${b.key} findings`"
            @click="goFindings(b.key)"
          >
            <i :style="{ background: CHART_PTYPE_RAMP[i % CHART_PTYPE_RAMP.length] }" />
            {{ b.key }}<AppIcon class="cell-go" name="chevron" :size="11" /> <b>{{ fmt(b.count) }}</b>
          </button>
        </div>
      </template>
      <p v-else class="empty-row">
        Awaiting package-type data. Populates as the next scan cycles re-observe images.
      </p>
    </div>
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
}
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 0;
}
.card-head h2 {
  margin: 0;
  font-size: var(--text-card-title);
  font-weight: 600;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.card-body {
  padding: 10px 16px 14px;
}

.donut-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 6px;
}
.donut-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-sweep-strong);
  color: var(--soft);
  border: none;
  background: none;
  padding: 2px 4px;
  border-radius: 5px;
  cursor: default;
  text-align: left;
  transition: background var(--dur-quick);
}
.donut-row:hover {
  background: var(--control-hover-bg);
  color: var(--ink);
}
.donut-row:active {
  background: var(--control-active-bg);
}
.donut-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.donut-row:hover .cell-go {
  color: var(--coral-text);
}
.donut-row i {
  width: 9px;
  height: 9px;
  border-radius: 2px;
  flex: none;
}
.donut-row b {
  margin-left: auto;
  color: var(--ink);
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}
</style>

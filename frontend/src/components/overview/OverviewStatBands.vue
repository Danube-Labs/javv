<script setup lang="ts">
/**
 * The Overview KPI + signal bands (issue 384 split — extracted from OverviewView, no behavior
 * change). Joined hairline-divided stat grammar (base.css owns the skin, issue 368); every
 * number is a server aggregation read through the scanner lens; every cell click-throughs to
 * the findings grid. Overview passes the facets it read for all its panels; on a dashboard the
 * bands read their own (useFindingsFacets), with the panel's filters in the read and the links.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import type { ViewPreset } from '@/api/generated'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useFindingsFacets, type Facets, type FacetsQuery } from '@/composables/useFindingsFacets'
import { panelFindingsQuery, panelQuery } from '@/dashboards/panelFilters'
import { CHART_SEV, type Severity } from '@/styles/tokens'
import { facetCount, fmt, type ScannerLens } from '@/lib/scannerLens'

const KPI_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']

const props = defineProps<{
  scanner: ScannerLens
  /** the screen's facets read; without it the bands read their own for `query` */
  facets?: Facets
  query?: FacetsQuery | null
  /** a dashboard panel's own filters (issue 999) */
  filters?: ViewPreset | null
}>()

const router = useRouter()
const { facets, settled, failed } = useFindingsFacets(
  () => props.facets,
  () => props.query && panelQuery(props.query, props.filters),
)

const count = (facet: string, key: string) => facetCount(facets.value, facet, key, props.scanner)
const sevCount = (s: Severity) => count('severity', s)
const totalPresent = computed(() => count('present', 'true'))
/** empty is judged across both scanners: one scanner's zero is a number to show, not "no data" */
const hasData = computed(() => facetCount(facets.value, 'present', 'true', 'all') > 0)
const fixableCount = computed(() => count('fixable', 'true'))
const fixPct = computed(() =>
  totalPresent.value === 0 ? 0 : Math.round((fixableCount.value / totalPresent.value) * 100),
)

/* 1b quick views — all straight facet reads */
const kevCount = computed(() => count('kev', 'true'))
const disagreeCount = computed(() => count('disagree', 'true'))
const stateCount = (k: string) => count('state', k)
const handledCount = computed(
  () => stateCount('resolved') + stateCount('not_affected') + stateCount('risk_accepted'),
)
const triage = computed(() => {
  const open = stateCount('open')
  const ack = stateCount('acknowledged')
  const stale = stateCount('stale')
  const handled = handledCount.value
  const total = open + ack + stale + handled
  const pct = (n: number) => (total === 0 ? 0 : (n / total) * 100)
  return { open, ack, stale, handled, total, pct }
})

function goFindings(query: Record<string, string>) {
  void router.push({ path: '/findings', query: panelFindingsQuery(props.filters, query) })
}
</script>

<template>
  <UiSkeleton v-if="!settled" :height="242" label="Loading findings summary" />
  <p v-else-if="failed" class="empty-row" role="alert">Findings summary unavailable.</p>
  <p v-else-if="!hasData" class="empty-row">No findings at this time.</p>
  <!-- KPI band: joined, hairline-divided (Nuxt stat grammar on our tokens) -->
  <div v-if="settled && !failed && hasData" class="stat-band">
    <button
      v-for="s in KPI_SEVERITIES"
      :key="s"
      class="stat-cell"
      :title="`Open findings filtered to ${s}`"
      @click="goFindings({ severity: s })"
    >
      <span class="stat-label"><i class="stat-dot" :style="{ background: CHART_SEV[s] }" />{{ s }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num">{{ fmt(sevCount(s)) }}</span>
    </button>
    <button class="stat-cell" title="Open findings with a fix available" @click="goFindings({ attr: 'fixable' })">
      <span class="stat-label"><i class="stat-dot" style="background: var(--teal)" />fix available<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num">{{ fixPct }}%</span>
      <span class="stat-sub">{{ fmt(fixableCount) }} findings patchable today</span>
    </button>
  </div>

  <!-- signal band (1b): urgency + quality quick views, same joined grammar -->
  <div v-if="settled && !failed && hasData" class="stat-band signal-band">
    <button class="stat-cell" title="Open known-exploited findings" @click="goFindings({ attr: 'kev' })">
      <span class="stat-label"><i class="stat-dot" style="background: var(--kev-bg)" />KEV · known-exploited<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num" :class="{ 'stat-num--alarm': kevCount > 0 }">{{ fmt(kevCount) }}</span>
    </button>
    <button class="stat-cell" title="Open findings where the scanners disagree" @click="goFindings({ attr: 'disagree' })">
      <span class="stat-label"><i class="stat-dot" style="background: var(--sev-medium-solid)" />scanners disagree<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num">{{ fmt(disagreeCount) }}</span>
    </button>
    <button class="stat-cell" title="Open the untriaged queue" @click="goFindings({ state: 'open' })">
      <span class="stat-label"><i class="stat-dot" style="background: var(--state-resolved-fg)" />triage progress<AppIcon class="cell-go" name="chevron" :size="11" /></span>
      <span class="stat-num"><span v-if="triage.total === 0" class="muted-dash">-</span><template v-else>{{ `${Math.round(triage.pct(triage.handled + triage.ack))}%` }}</template></span>
      <span class="progress-bar" aria-hidden="true">
        <i class="seg-open" :style="{ width: `${triage.pct(triage.open)}%` }" />
        <i class="seg-ack" :style="{ width: `${triage.pct(triage.ack)}%` }" />
        <i class="seg-handled" :style="{ width: `${triage.pct(triage.handled)}%` }" />
        <i class="seg-stale" :style="{ width: `${triage.pct(triage.stale)}%` }" />
      </span>
      <span class="stat-sub">{{ fmt(triage.open) }} open · {{ fmt(triage.ack) }} ack · {{ fmt(triage.handled) }} handled<template v-if="triage.stale"> · {{ fmt(triage.stale) }} stale</template></span>
    </button>
  </div>
</template>

<style scoped>
/* the joined stat-band SKIN lives in base.css (issue 368) — only this screen's layout here */
.stat-band {
  grid-template-columns: repeat(5, 1fr);
}
.signal-band {
  grid-template-columns: repeat(3, 1fr);
  margin-top: 12px;
}

.progress-bar {
  display: flex;
  width: 100%;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
  margin-top: 8px;
  background: var(--line2);
}
.progress-bar i {
  height: 100%;
}
.seg-open {
  background: var(--state-open-solid);
}
.seg-ack {
  background: var(--triage-seg-ack);
}
.seg-handled {
  background: var(--triage-seg-handled);
}
.seg-stale {
  background: var(--state-stale-line);
}
@media (max-width: 1120px) {
  .stat-band {
    grid-template-columns: repeat(2, 1fr);
  }
  .stat-cell + .stat-cell {
    border-left: none;
  }
}
/* a Half panel of a dashboard, whose cell is a size container: five numbers do not fit in a row,
   so the bands take three columns at any screen width. Overview declares no container. */
@container (max-width: 700px) {
  .stat-band {
    grid-template-columns: repeat(3, 1fr);
  }
  .stat-cell + .stat-cell {
    border-left: 1px solid var(--line2);
  }
  .stat-cell:nth-child(3n + 1) {
    border-left: none;
  }
  .stat-cell:nth-child(n + 4) {
    border-top: 1px solid var(--line2);
  }
}
</style>

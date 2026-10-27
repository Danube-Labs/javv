<script setup lang="ts">
/**
 * Overview — single-cluster dashboard (M9c slice 1; SCREENS §2, prototype screens-overview.jsx
 * ported structure-only onto tokens). KPI strip is the joined hairline-divided stat band (Nuxt UI
 * stat grammar — operator ruling from the finding-detail risk band) with click-through cells.
 * Every number is a server aggregation; the scanner seg only re-reads the by_scanner splits the
 * server already returned. Cut vs prototype (recorded in the bolt README): KPI sparklines +
 * "+new 30d" chips (no per-severity trend agg), namespace severity MixBar (no per-ns severity
 * agg), Top components / Language binaries / Newly published (B-6/B-2).
 * Issue-384 split: the stat bands, the package types and the namespaces card live in
 * components/overview/;
 * the scanner-lens count math is the shared pure helper lib/scannerLens.ts.
 * The Scan-activity card is gone (it duplicated IngestLens — same trends/scans read); its slot
 * runs the A/B specimens (TopComponentsCard vs RiskiestImagesCard) pending the §8.5 ruling.
 */
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'

import { buildFindingsTrendOption, emptyTrendNote } from '@/charts/buildFindingsTrendOption'
import { buildSeverityTrendOption, type SeverityTrendData } from '@/charts/buildSeverityTrendOption'
import { isSubDayWindow } from '@/charts/buildTrendQuery'
import EChart from '@/components/charts/EChart.vue'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import OverviewNamespacesCard from '@/components/overview/OverviewNamespacesCard.vue'
import OverviewStatBands from '@/components/overview/OverviewStatBands.vue'
import PackageTypeCard from '@/components/overview/PackageTypeCard.vue'
import RiskiestImagesCard from '@/components/overview/RiskiestImagesCard.vue'
import TopComponentsCard from '@/components/overview/TopComponentsCard.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useApi } from '@/composables/useApi'
import { useStretchWidth } from '@/composables/useStretchWidth'
import { useClusterStore } from '@/stores/cluster'
import { useOverviewStore } from '@/stores/overview'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { SCANNER_SWITCH_OPTS, type ScannerLens } from '@/lib/scannerLens'
import { ref } from 'vue'

const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const overview = useOverviewStore()
const { withGlobals } = useApi()

const scanner = ref<ScannerLens>('all')

/** The header card stretches when the last sweep time arrives (issue 902). */
const headCard = ref<HTMLElement | null>(null)
useStretchWidth(headCard)
const LENS_OPTS = [
  { value: 'scanner', label: 'by scanner' },
  { value: 'severity', label: 'by severity' },
] as const
const trendLens = ref<'scanner' | 'severity'>('scanner')

watch(
  () => [clusterStore.selectedId, timeTravel.t, timeTravel.windowDays] as const,
  ([id, t]) => {
    if (!id) return
    void overview.load(withGlobals({ cluster_id: id }), timeTravel.windowDays)
    if (t !== null) trendLens.value = 'scanner' // severity lens is a now-only read (route 422s)
  },
  { immediate: true },
)
watch(
  [trendLens, scanner, () => clusterStore.selectedId, () => timeTravel.windowDays],
  ([lens, sc, id]) => {
    if (lens === 'severity' && id && timeTravel.isNow) {
      void overview.loadSeverityTrend(id, timeTravel.windowDays, sc === 'all' ? null : sc)
    }
  },
)

const trendOption = computed(() => {
  if (trendLens.value === 'severity') {
    return buildSeverityTrendOption(overview.sevTrend as SeverityTrendData)
  }
  if (scanner.value === 'all') return buildFindingsTrendOption(overview.trend)
  return buildFindingsTrendOption({
    new: { [scanner.value]: overview.trend.new[scanner.value] },
    resolved: { [scanner.value]: overview.trend.resolved[scanner.value] },
  })
})
const trendNote = computed(() =>
  trendLens.value === 'severity' && overview.sevTrendLoading
    ? null
    : emptyTrendNote(trendOption.value, trendLens.value),
)

const lastSweep = computed(() => {
  if (!overview.lastIngestAt) return null
  return new Date(overview.lastIngestAt).toLocaleString('en-GB', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
})

const subDayNote = computed(() => isSubDayWindow(timeTravel.windowDays))

function goFindings(query: Record<string, string>) {
  void router.push({ path: '/findings', query })
}
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div ref="headCard" class="head-card head-card-fluid">
        <h1>Overview</h1>
        <p class="head-note">
          Current state across <b class="mono-cell"><template v-if="clusterStore.selected?.cluster_name">{{ clusterStore.selected.cluster_name }}</template><span v-else class="muted-dash">-</span></b>
          <template v-if="lastSweep"> · last sweep <span class="mono-cell">{{ lastSweep }}</span></template>
        </p>
      </div>
      <div class="head-actions">
        <UiSegControl v-model="scanner" :options="SCANNER_SWITCH_OPTS" label="Scanner" />
        <UiButton variant="primary" @click="goFindings({ severity: 'critical' })">
          Triage critical <AppIcon name="chevron" :size="13" />
        </UiButton>
      </div>
    </div>

    <IngestLens
      v-if="clusterStore.selectedId"
      class="ov-lens"
      :cluster-id="clusterStore.selectedId"
      subject="this screen"
    />

    <div v-if="overview.loading" class="skel-stack" aria-busy="true" aria-label="Loading overview">
      <UiSkeleton :height="96" />
      <UiSkeleton :height="300" />
    </div>

    <p v-else-if="overview.failed" class="load-error" role="alert">
      Overview unavailable. Check the backend connection.
    </p>

    <EmptyState
      v-else-if="overview.empty"
      icon="pulse"
      title="No sweep has landed yet"
      hint="KPIs and trends appear after the first scanner cycle commits. Scanner status shows per-scanner progress."
    />

    <template v-else>
      <!-- one facets read feeds the bands, the package types and the namespaces, so their
           numbers cannot disagree (DESIGN.md §10); on a dashboard each reads its own -->
      <OverviewStatBands :scanner="scanner" :facets="overview.facets" />

      <div class="grid grid-2-1">
        <section class="card">
          <div class="card-head">
            <div>
              <h2>Vulnerabilities over time</h2>
              <p class="card-sub">
                new per day · {{ timeTravel.windowLabel.toLowerCase() }}<template
                  v-if="trendLens === 'scanner'"
                > · resolved = scan-observed</template>
              </p>
            </div>
            <UiSegControl
              v-if="timeTravel.isNow"
              v-model="trendLens"
              :options="LENS_OPTS"
              label="Group the chart"
            />
          </div>
          <div class="card-body">
            <p v-if="trendNote" class="empty-row trend-empty">{{ trendNote }}</p>
            <EChart v-else :option="trendOption" :height="250" />
            <p v-if="subDayNote" class="chart-note">
              Trend at daily resolution: chart covers the last 1 day.
            </p>
          </div>
        </section>
        <PackageTypeCard :scanner="scanner" :facets="overview.facets" />
      </div>

      <div class="grid grid-1-1">
        <!-- both board cards ship (§8.5 specimens): components answer "what to upgrade",
             images answer "what to rebuild" — the pair is the point, not a duplication -->
        <TopComponentsCard :scanner="scanner" />
        <RiskiestImagesCard :scanner="scanner" />
      </div>

      <div class="grid">
        <OverviewNamespacesCard :scanner="scanner" :facets="overview.facets" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.ov-lens {
  margin-bottom: 16px;
}
.screen-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
/* at the 1024 floor the title card gives way (its sentence wraps) and the actions stay whole on
   the title's row; the shared head-card is `flex: none`, so this screen opts in (issue 652) */
.screen-head .head-card {
  flex: 0 1 auto;
  min-width: 0;
}
.head-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 10px;
}

.grid {
  display: grid;
  gap: var(--grid-gap);
  margin-top: 16px;
}
/* grid children default to min-width:auto — an ECharts canvas's rendered width then pins the
   column and expanding the sidebar shoves the row off-viewport; 0 lets autoresize shrink it */
.grid > * {
  min-width: 0;
}
.grid-2-1 {
  grid-template-columns: 1.55fr 1fr;
}
.grid-1-1 {
  grid-template-columns: 1fr 1fr;
}
@media (max-width: 1120px) {
  .grid-2-1,
  .grid-1-1 {
    grid-template-columns: 1fr;
  }
}

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
/* holds the chart's height, so the card doesn't jump when a range turns up empty */
.trend-empty {
  display: grid;
  place-items: center;
  min-height: 250px;
  margin: 0;
}
.chart-note {
  margin: 6px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}

.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
.skel-stack > * + * {
  margin-top: 16px;
}
</style>

<script setup lang="ts">
/**
 * All clusters — fleet landing page (M9c slice 2; SCREENS §1). Same joined stat grammar as
 * Overview. Every per-cluster number is a server aggregation (facets/freshness/inventory, one
 * set per row); the fleet strip adds those server buckets ACROSS CLUSTERS — the only roll-up
 * available before the v1.1 metrics rollup — never across scanners (the seg lens picks the
 * server's by_scanner split, exactly like Overview). I3: at T<now the store goes `limited`,
 * the screen renders LimitedHistoricalNotice, and no query is emitted (unit-guarded).
 * Issue-384 split: the fleet table lives in components/dashboards/FleetTable.vue; the
 * scanner-lens bucket math is the shared pure helper lib/scannerLens.ts.
 */
import { computed, ref, watch } from 'vue'

import FleetTable from '@/components/dashboards/FleetTable.vue'
import LimitedHistoricalNotice from '@/components/dashboards/LimitedHistoricalNotice.vue'
import { useAllClustersStore } from '@/stores/allClusters'
import { useStalenessStore } from '@/stores/staleness'
import { useTimeTravelStore } from '@/stores/timeTravel'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useStretchWidth } from '@/composables/useStretchWidth'
import { CHART_SEV, type Severity } from '@/styles/tokens'
import { freshnessStatus } from '@/system/freshness'
import { facetCount, fmt, SCANNER_LENS_OPTS, type ScannerLens } from '@/lib/scannerLens'

const KPI_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'negligible']
const timeTravel = useTimeTravelStore()
const fleet = useAllClustersStore()
// health chips threshold on the live FLEET-default window (a per-cluster override is the
// banner's concern; this cross-cluster surface uses the one shared default)
const staleness = useStalenessStore()
void staleness.loadFleet()

const scanner = ref<ScannerLens>('all')

/** The header card stretches when the fleet counts arrive (issue 902). */
const headCard = ref<HTMLElement | null>(null)
useStretchWidth(headCard)

watch(
  () => timeTravel.t,
  (t) => void fleet.load(t),
  { immediate: true },
)

/** Fleet strip: per-severity server buckets added across clusters (see header). */
const fleetSev = (sev: Severity) =>
  fleet.rows.reduce((n, r) => n + facetCount(r.facets, 'severity', sev, scanner.value), 0)

const needAttention = computed(
  () =>
    fleet.rows.filter(
      (r) => r.failed || freshnessStatus(r.freshness, staleness.fleetThresholdS) !== 'ok',
    ).length,
)
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div ref="headCard" class="head-card head-card-fluid">
        <h1>All clusters</h1>
        <p class="head-note">
          <template v-if="fleet.limited">Historical fleet view, limited until the v1.1 rollup</template>
          <template v-else>
            Fleet current state
            <!-- the counts are not known while the fleet loads: no "0 clusters" in the meantime -->
            <template v-if="!fleet.loading">
              · <b class="mono-cell">{{ fleet.rows.length }}</b>
              cluster{{ fleet.rows.length === 1 ? '' : 's' }}
              <template v-if="fleet.rows.length">
                · <span v-if="needAttention" class="deg-note">{{ needAttention }} need{{ needAttention === 1 ? 's' : '' }} attention</span>
                <template v-else>all healthy</template>
              </template>
            </template>
          </template>
        </p>
      </div>
      <div v-if="!fleet.limited" class="head-actions">
        <UiSegControl v-model="scanner" :options="SCANNER_LENS_OPTS" />
      </div>
    </div>

    <LimitedHistoricalNotice v-if="fleet.limited" />

    <div v-else-if="fleet.loading" class="skel-stack" aria-busy="true" aria-label="Loading clusters">
      <UiSkeleton :height="96" />
      <UiSkeleton :height="300" />
    </div>

    <p v-else-if="fleet.failed" class="load-error" role="alert">
      Cluster list unavailable. Check the backend connection.
    </p>

    <div v-else-if="fleet.rows.length === 0" class="first-run">
      <h2>No clusters yet</h2>
      <p>
        A cluster appears here once its scanner token is minted and the first sweep lands.
        Tokens are minted in Settings.
      </p>
    </div>

    <template v-else>
      <!-- fleet strip: same joined grammar as Overview, read-only (a fleet severity has no
           single destination — findings are per-cluster; rows below are the drill-down) -->
      <div class="stat-band fleet-band">
        <div class="stat-cell">
          <span class="stat-label"><i class="stat-dot" style="background: var(--slate)" />clusters</span>
          <span class="stat-num">{{ fmt(fleet.rows.length) }}</span>
        </div>
        <div v-for="s in KPI_SEVERITIES" :key="s" class="stat-cell">
          <span class="stat-label"><i class="stat-dot" :style="{ background: CHART_SEV[s] }" />{{ s }}</span>
          <span class="stat-num">{{ fmt(fleetSev(s)) }}</span>
        </div>
      </div>

      <FleetTable :scanner="scanner" :threshold-s="staleness.fleetThresholdS" />
    </template>
  </div>
</template>

<style scoped>
.screen-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* joined stat band (Nuxt stat grammar) — fleet cells are read-only: no wash, no chevron
   (never dress a cell whose destination doesn't exist) */
/* the joined stat-band SKIN lives in base.css (issue 368) — only this screen's layout here */
.fleet-band {
  grid-template-columns: repeat(6, 1fr);
}

.deg-note {
  color: var(--health-degraded-fg);
  font-weight: 600;
}

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

.skel-stack > * + * {
  margin-top: 16px;
}
</style>

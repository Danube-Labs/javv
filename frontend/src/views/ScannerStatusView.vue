<script setup lang="ts">
/**
 * Scanner status screen (M9d slice 2; SCREENS §12, C-3 redesign): the shared data-screen
 * band (head-card + the scan-ingest lens — the same "committed runs per bucket, per scanner"
 * strip findings/images carry, operator ruling 2026-07-12, joined here by the failed-ingests
 * strip on the same axis, issue 575) over per-(cluster, scanner) cards
 * — D20 freshness + D41 read-only provenance + last-N committed runs + the pushes the backend
 * refused (issue 357; one self-contained panel per scanner, so no count ever mixes them).
 * Retry and dead-letter stay cut (A-7/D-4): they are scanner-local, so the panel is read-only.
 * Freshness/provenance are NOW-truth reads — at a rewound T the screen renders the C-1/D39
 * limitation notice instead of data.
 */
import { computed, ref, watch } from 'vue'

import {
  scannerFreshnessApiV1ScannersFreshnessGet,
  scannerProvenanceApiV1ScannersProvenanceGet,
} from '@/api/generated'
import { client } from '@/api/client'
import FailedIngestsLens from '@/components/dashboards/FailedIngestsLens.vue'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import IngestFailuresTable from '@/components/scanners/IngestFailuresTable.vue'
import LimitedHistoricalNotice from '@/components/dashboards/LimitedHistoricalNotice.vue'
import ScannerRunsTable from '@/components/scanners/ScannerRunsTable.vue'
import ScannerStatusCard, {
  type ProvenanceRow,
} from '@/components/scanners/ScannerStatusCard.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { readFailureCopy } from '@/findings/failureCopy'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import type { FreshnessRow } from '@/system/freshness'
import type { ScannerName } from '@/system/ingestFailures'

const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()

const RUNS_FETCHED = 50 // the provenance endpoint's own last-N cap; GridPager slices it

const freshness = ref<FreshnessRow[]>([])
const provenance = ref<ProvenanceRow[]>([])
const loading = ref(true)
const failed = ref(false)
const failedStatus = ref<number | null>(null)

watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  async ([id, t]) => {
    if (!id || t !== null) return // T<now renders the limitation notice, no reads (C-1/D39)
    loading.value = true
    const [fresh, prov] = await Promise.all([
      scannerFreshnessApiV1ScannersFreshnessGet({ client, query: { cluster_id: id } }),
      scannerProvenanceApiV1ScannersProvenanceGet({
        client,
        query: { cluster_id: id, runs: RUNS_FETCHED } as never,
      }),
    ])
    loading.value = false
    failed.value = !fresh.response?.ok || !prov.response?.ok || !fresh.data || !prov.data
    failedStatus.value = (fresh.response?.ok ? prov.response?.status : fresh.response?.status) ?? null
    if (failed.value) {
      logger.warn('scanner_status_failed', {
        freshness: fresh.response?.status,
        provenance: prov.response?.status,
      })
      return
    }
    freshness.value = (fresh.data as { scanners: FreshnessRow[] }).scanners ?? []
    provenance.value = (prov.data as { scanners: ProvenanceRow[] }).scanners ?? []
  },
  { immediate: true },
)

/** one card per scanner either read knows about — a scanner with freshness but no committed
 * run still shows (its card says so) */
const scanners = computed(() => {
  const names = new Set<string>([
    ...provenance.value.map((p) => p.scanner),
    ...freshness.value.map((f) => f.scanner),
  ])
  return [...names].sort().map((name) => ({
    name,
    provenance: provenance.value.find((p) => p.scanner === name) ?? null,
    freshness: freshness.value.find((f) => f.scanner === name) ?? null,
  }))
})

/** below 1100px the columns become one lane at a time, picked here (CSS hides the rest) */
const picked = ref('')
watch(
  scanners,
  (list) => {
    if (!list.some((s) => s.name === picked.value)) picked.value = list[0]?.name ?? ''
  },
  { immediate: true },
)
const laneOptions = computed(() =>
  scanners.value.map((s) => ({
    value: s.name,
    label: s.name,
    accent: `var(--scanner-${s.name}-fg)`,
  })),
)
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Scanner status</h1>
        <p class="head-stat">
          <!-- a count not yet read, or refused, is unknown, not zero (issue 833, F5) -->
          <template v-if="!loading && !failed">{{ scanners.length }}</template
          ><span v-else class="muted-dash">-</span><span class="head-unit"> scanners</span>
        </p>
        <p class="head-note">committed runs only · versions are read-only provenance</p>
      </div>
      <!-- one joined band: a day lines up across both strips, each on its own scale -->
      <div v-if="clusterStore.selectedId" class="lens-stack">
        <IngestLens :cluster-id="clusterStore.selectedId" subject="this screen" />
        <FailedIngestsLens
          :cluster-id="clusterStore.selectedId"
          :t="timeTravel.t"
          :window-days="timeTravel.windowDays"
        />
      </div>
    </div>

    <LimitedHistoricalNotice
      v-if="timeTravel.t !== null"
      title="Historical scanner status is limited until the v1.1 metrics rollup"
      body="Freshness and provenance answer for now. The committed-run history you can rewind
        lives in the ingest lens above. Return to now for live scanner health."
    />

    <template v-else>
      <div v-if="loading" class="scan-cards" aria-busy="true" aria-label="Loading scanner status">
        <UiSkeleton :height="300" />
        <UiSkeleton :height="300" />
      </div>

      <p v-else-if="failed" class="load-error" role="alert">
        {{ readFailureCopy(failedStatus, 'Scanner status unavailable. Check the backend connection.') }}
      </p>

      <div v-else-if="scanners.length === 0" class="not-found" role="status">
        <p>No scanner has reported for this cluster yet. The first committed run lands here.</p>
      </div>

      <template v-else>
        <div class="lane-pick">
          <UiSegControl v-model="picked" :options="laneOptions" />
        </div>
        <div class="lanes" :style="{ '--lanes': scanners.length }">
          <section
            v-for="s in scanners"
            :key="s.name"
            class="lane"
            :class="{ 'lane-off': s.name !== picked }"
            :data-scanner="s.name"
            :aria-label="`${s.name} scanner`"
          >
            <h2 class="lane-head">{{ s.name }}</h2>
            <ScannerStatusCard
              :scanner="s.name"
              :provenance="s.provenance"
              :freshness="s.freshness"
            />
            <!-- what needs attention sits right under the health card, above the run history -->
            <IngestFailuresTable
              :cluster-id="clusterStore.selectedId!"
              :scanner="s.name as ScannerName"
              :t="timeTravel.t"
              :window-days="timeTravel.windowDays"
            />
            <ScannerRunsTable
              v-if="(s.provenance?.runs ?? []).length"
              :runs="s.provenance!.runs!"
              :scanner="s.name"
              :cap="RUNS_FETCHED"
            />
          </section>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
/* prototype .scan-cards grid; band/head scaffolding lives in base.css */
/* The two strips as one band: a single outer frame, split by a canvas-coloured gutter so each
   lens reads as its own panel (operator ruling 2026-09-27, on built A/B/C specimens; a hairline
   alone read as one chart). The stack carries the frame, the lenses give up theirs — their roots
   take this scope, so this reaches them. */
.lens-stack {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--bg);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.lens-stack > .ingest-lens,
.lens-stack > .fail-lens {
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.lens-stack > .ingest-lens {
  border-bottom: 1px solid var(--line);
}
.lens-stack > .fail-lens {
  border-top: 1px solid var(--line);
}
.scan-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  align-items: start;
}
@media (width <= 1100px) {
  .scan-cards {
    grid-template-columns: 1fr;
  }
}
/* One lane per scanner, side by side (operator ruling 2026-09-27, on built A/B/C specimens).
   Each lane is a column of one shared 4-row subgrid, so a section starts on the same line in
   every lane however tall its neighbour above is. */
.lanes {
  display: grid;
  grid-template-columns: repeat(var(--lanes), minmax(0, 1fr));
  grid-template-rows: repeat(4, auto);
  column-gap: 28px;
}
.lane {
  display: grid;
  grid-row: 1 / span 4;
  grid-template-rows: subgrid;
  row-gap: 14px;
  min-width: 0;
}
/* Identity is carried by the lane head and by the lane's own table heads, which take the
   scanner hue instead of the shared slate band. Only --table-head-bg moves: --table-head-fg stays,
   and it clears AA on both hues (contrast-gate.spec.ts). */
.lane[data-scanner='trivy'] {
  --lane-hue: var(--scanner-trivy-fg);
}
.lane[data-scanner='grype'] {
  --lane-hue: var(--scanner-grype-fg);
}
.lane {
  --table-head-bg: var(--lane-hue, var(--slate2));
}
.lane-head {
  margin: 0;
  padding-bottom: 8px;
  border-bottom: 3px solid var(--lane-hue, var(--line));
  color: var(--lane-hue, var(--ink));
  font-size: var(--text-card-title);
  text-transform: capitalize;
}
/* the picker only exists where the lanes can't sit side by side */
.lane-pick {
  display: none;
  justify-content: center;
}
@media (width <= 1100px) {
  .lane-pick {
    display: flex;
  }
  .lanes {
    grid-template-columns: minmax(0, 1fr);
  }
  .lane-off {
    display: none;
  }
}
.load-error {
  margin: 0;
}
.not-found {
  padding: var(--space-8) 0;
  text-align: center;
  color: var(--soft);
}
</style>

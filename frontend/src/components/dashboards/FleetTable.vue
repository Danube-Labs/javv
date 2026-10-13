<script setup lang="ts">
/**
 * The fleet table (issue 384 split — extracted from AllClustersView, no behavior change):
 * one row per cluster, every number a server aggregation read through the scanner lens;
 * per-scanner severity mix bars are never merged; a row click selects the cluster and opens
 * its Overview. The flush card grammar: no head, no inner panel — the table IS the card.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import DotWord from '@/components/chips/DotWord.vue'
import HealthChip from '@/components/chips/HealthChip.vue'
import MixBar from '@/components/dashboards/MixBar.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import RowLink from '@/components/ui/RowLink.vue'
import { useNow } from '@/composables/useNow'
import { useAllClustersStore, type ClusterRow } from '@/stores/allClusters'
import { useClusterStore } from '@/stores/cluster'
import type { Severity } from '@/styles/tokens'
import { facetCount, fmt, type ScannerLens } from '@/lib/scannerLens'
import { lastDataAt } from '@/system/freshness'
import { RETIREMENT_TICK_MS, retirementChip, retirementStatus } from '@/system/retirement'

const MIX_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'negligible', 'unknown']
const SCANNERS = ['trivy', 'grype'] as const

const props = defineProps<{ scanner: ScannerLens; thresholdS: number }>()

const router = useRouter()
const clusterStore = useClusterStore()
const fleet = useAllClustersStore()
// the retirement countdown per cluster, inside its warning window only (issue 765). It moves on
// the banner's tick, from the list the banner re-reads, so a cluster that scans again loses its
// chip without a reload (issue 787)
const now = useNow(RETIREMENT_TICK_MS)
const retiring = computed(() => {
  const listed = new Map(clusterStore.clusters.map((c) => [c.cluster_id, c]))
  return new Map(
    fleet.rows.map((r) => [
      r.cluster_id,
      retirementChip(retirementStatus(listed.get(r.cluster_id) ?? r.schedule, now.value), fleet.rows.length === 1),
    ]),
  )
})

const count = (row: ClusterRow, facet: string, key: string) =>
  facetCount(row.facets, facet, key, props.scanner)
const presentCount = (row: ClusterRow) => count(row, 'present', 'true')

/* per-row signals — all straight facet reads the row already fetched (Overview 1b analogs) */
const kevCount = (row: ClusterRow) => count(row, 'kev', 'true')
const disagreeCount = (row: ClusterRow) => count(row, 'disagree', 'true')
const fixPct = (row: ClusterRow) => {
  const present = presentCount(row)
  return present === 0 ? 0 : Math.round((count(row, 'fixable', 'true') / present) * 100)
}
function triage(row: ClusterRow) {
  const open = count(row, 'state', 'open')
  const ack = count(row, 'state', 'acknowledged')
  const stale = count(row, 'state', 'stale')
  const handled =
    count(row, 'state', 'resolved') +
    count(row, 'state', 'not_affected') +
    count(row, 'state', 'risk_accepted')
  const total = open + ack + stale + handled
  const pct = (n: number) => (total === 0 ? 0 : (n / total) * 100)
  return { open, ack, stale, handled, total, pct }
}

/** One mix bar per scanner (never merged): that scanner's by_scanner severity buckets. */
function mixFor(row: ClusterRow, sc: (typeof SCANNERS)[number]): Partial<Record<Severity, number>> {
  return Object.fromEntries(
    MIX_SEVERITIES.map((sev) => [
      sev,
      row.facets.severity?.find((x) => x.key === sev)?.by_scanner[sc] ?? 0,
    ]),
  )
}
const visibleScanners = computed(() =>
  props.scanner === 'all' ? SCANNERS : ([props.scanner] as const),
)

const lastSweep = (row: ClusterRow) => {
  const latest = row.freshness
    .map((r) => r.last_ingest_at)
    .filter((v): v is string => v !== null)
    .sort()
    .at(-1)
  return latest ? lastDataAt(latest) : null
}

function open(row: ClusterRow) {
  clusterStore.select(row.cluster_id)
  void router.push('/overview')
}
// the address a new tab needs: the shell restores the cluster from the query on a cold load.
// A plain click still goes through `open`, which selects first and then navigates.
const overviewRoute = (row: ClusterRow) => ({ path: '/overview', query: { cluster: row.cluster_id } })
</script>

<template>
  <!-- flush table card (prototype fleet-card): no head, no inner panel — the table IS the card -->
  <section class="card fleet-card tbl-scroll-pin">
      <table class="tbl tbl-hover">
        <thead>
          <tr>
            <th>Cluster</th>
            <th class="r">Health</th>
            <th>Severity mix</th>
            <th class="r">Findings</th>
            <th class="r">KEV</th>
            <th class="r">Fix %</th>
            <th class="r">Disagree</th>
            <th class="r">Triage</th>
            <th class="r">Images</th>
            <th class="r">Replicas</th>
            <th class="r">Last sweep</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in fleet.rows"
            :key="row.cluster_id"
            :title="`Open ${row.cluster_name} overview`"
            @click="open(row)"
          >
            <td>
              <div class="cluster-cell">
                <span class="glyph" aria-hidden="true">{{ (row.cluster_name[0] ?? '?').toUpperCase() }}</span>
                <div class="cluster-info">
                  <RowLink :to="overviewRoute(row)" @open="open(row)">
                    <span class="cl-name cl-link">{{ row.cluster_name }}<AppIcon class="cell-go" name="chevron" :size="11" /></span>
                  </RowLink>
                  <span v-if="row.cluster_name !== row.cluster_id" class="cl-id mono-cell">{{ row.cluster_id }}</span>
                  <DotWord
                    v-if="retiring.get(row.cluster_id)"
                    :tone="retiring.get(row.cluster_id)!.tone"
                    :label="retiring.get(row.cluster_id)!.label"
                  />
                </div>
              </div>
            </td>
            <td class="r"><HealthChip :rows="row.freshness" :threshold-s="thresholdS" /></td>
            <td class="mix-cell">
              <template v-if="!row.failed">
                <MixBar
                  v-for="sc in visibleScanners"
                  :key="sc"
                  :counts="mixFor(row, sc)"
                  :label="sc"
                  numbers
                  class="mix-stack"
                />
              </template>
              <span v-else class="row-degraded">unavailable</span>
            </td>
            <td class="r mono-cell"><span v-if="row.failed" class="muted-dash">-</span><b v-else>{{ fmt(presentCount(row)) }}</b></td>
            <td class="r mono-cell">
              <span v-if="row.failed" class="muted-dash">-</span><b v-else :class="{ 'kev-alarm': kevCount(row) > 0 }">{{ fmt(kevCount(row)) }}</b>
            </td>
            <td class="r mono-cell"><span v-if="row.failed" class="muted-dash">-</span><template v-else>{{ `${fixPct(row)}%` }}</template></td>
            <td class="r mono-cell"><span v-if="row.failed" class="muted-dash">-</span><template v-else>{{ fmt(disagreeCount(row)) }}</template></td>
            <td class="r triage-cell">
              <template v-if="!row.failed && triage(row).total > 0">
                <span class="progress-bar" aria-hidden="true">
                  <i class="seg-open" :style="{ width: `${triage(row).pct(triage(row).open)}%` }" />
                  <i class="seg-ack" :style="{ width: `${triage(row).pct(triage(row).ack)}%` }" />
                  <i class="seg-handled" :style="{ width: `${triage(row).pct(triage(row).handled)}%` }" />
                  <i class="seg-stale" :style="{ width: `${triage(row).pct(triage(row).stale)}%` }" />
                </span>
                <span class="triage-pct mono-cell">{{ Math.round(triage(row).pct(triage(row).handled + triage(row).ack)) }}%</span>
              </template>
              <span v-else class="muted-dash">-</span>
            </td>
            <td class="r mono-cell"><span v-if="row.imagesCount === null" class="muted-dash">-</span><template v-else>{{ fmt(row.imagesCount) }}</template></td>
            <td class="r mono-cell"><span v-if="row.replicas === null" class="muted-dash">-</span><template v-else>{{ fmt(row.replicas) }}</template></td>
            <td class="r mono-cell sweep-cell">{{ lastSweep(row) ?? 'never' }}</td>
          </tr>
        </tbody>
      </table>
  </section>
  <p class="fleet-note">
    <AppIcon name="layers" :size="13" />
    Each cluster's scanner module pushes independently over HTTPS with its own API token:
    a cluster going quiet shows up here, not as missing data downstream.
  </p>
</template>

<style scoped>
/* flush table card (prototype fleet-card): the table IS the card — no head, no inner panel */
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  margin-top: 16px;
}
.fleet-card .tbl th:first-child,
.fleet-card .tbl td:first-child {
  padding-left: 16px;
}
.fleet-card .tbl th:last-child,
.fleet-card .tbl td:last-child {
  padding-right: 16px;
}
.fleet-card .tbl tbody tr:last-child td {
  border-bottom: 0;
}
.fleet-note {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 10px 2px 0;
  font-size: var(--text-sm);
  color: var(--soft);
}

.tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-body);
}
.tbl th {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--soft);
  text-align: left;
  padding: 7px 12px;
  border-bottom: 1px solid var(--line2);
  background: var(--panel);
}
.tbl td {
  padding: 9px 12px;
  border-bottom: 1px solid var(--line2);
  vertical-align: middle;
}
/* anchored numeric columns (operator A/B ruling, sharpened live twice): shrink-to-content +
   nowrap, HAIRLINE COLUMN DIVIDERS (the stat-band grammar carried into the table), and the
   value CENTERED + weighted in its bounded cell — right-hugging regular-weight digits at the
   top of a tall row read as floating */
.tbl th + th,
.tbl td + td {
  border-left: 1px solid var(--line2);
}
/* the header's dividers live on the slate band — the beige hairline slits it */
.tbl.tbl th + th {
  border-left-color: var(--table-head-line);
}
/* .tbl.tbl matches the base-skin weight — this screen's centered-value ruling must outrank
   the shared right-align default */
.tbl.tbl th.r,
.tbl.tbl td.r {
  text-align: center;
  width: 1%;
  white-space: nowrap;
}
.tbl.tbl td.r {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.tbl-hover tbody tr {
  cursor: default; /* arrow, not the I-beam — text stays selectable */
  transition: background var(--dur-quick);
}
.tbl-hover tbody tr:hover {
  background: var(--row-hover);
}
.tbl-hover tbody tr:active {
  background: var(--line2);
}

.cluster-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}
.glyph {
  width: 26px;
  height: 26px;
  border-radius: 7px;
  background: var(--slate);
  color: var(--side-brand-fg);
  display: grid;
  place-items: center;
  font-weight: 600;
  font-size: var(--text-body);
  flex: none;
}
.cluster-info {
  display: flex;
  flex-direction: column;
}
.cl-name {
  display: inline-flex;
  align-items: center;
  font-weight: 600;
  color: var(--ink);
}
.cl-id {
  font-size: var(--text-sm);
  color: var(--soft);
  margin-top: 2px;
}
/* the affordance carrier — same convention as the grid's cve-link */
.cl-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .cl-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.mix-cell {
  min-width: 180px;
}
/* wider than MixBar's own bar→counts gap, so each scanner's bar and counts read as one unit */
.mix-stack + .mix-stack {
  margin-top: 12px;
}

/* per-row signals (A/B under review) — same seg colors as the Overview triage bar */
.kev-alarm {
  color: var(--sev-critical-fg);
}
.progress-bar {
  display: flex;
  width: 90px;
  height: 6px;
  border-radius: 3px;
  overflow: hidden;
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
.triage-cell {
  white-space: nowrap;
  width: 1%;
}
.triage-cell .progress-bar {
  display: inline-flex;
  vertical-align: middle;
}
.triage-pct {
  font-size: var(--text-sm);
  color: var(--soft);
  margin-left: 8px;
}
.row-degraded {
  font-size: var(--text-sm);
  color: var(--soft);
}

@media (prefers-reduced-motion: reduce) {
  .tbl-hover tbody tr,
  .cl-link {
    transition: none;
  }
}
</style>

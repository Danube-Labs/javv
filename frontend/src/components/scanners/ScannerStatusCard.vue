<script setup lang="ts">
/**
 * Per-(cluster, scanner) status panel (M9d slice 2; SCREENS §12, C-3 redesign) — ports the
 * prototype's `ScannerStatusCard` + `.scan-*` CSS onto tokens; type follows the app grammar,
 * not the prototype's (stats = the head-stat mono, labels = the table-header ink/700 —
 * operator rulings 2026-07-11/12: soft small caps read faint). The prototype's ingest/failed
 * stats are CUT (A-7/D-4: dead-lettering is scanner-local, there is no failed-ingest feed);
 * the stats read the latest COMMITTED run (catalog-first provenance, never latest-doc, D40).
 * Version + vuln-DB lines are D41 provenance: read-only display of what the last committed
 * run ingested — operators change versions by swapping the published image tag (GitOps),
 * never here. Staleness is HealthChip's dot-and-word grammar on the D20 freshness row. The
 * committed-runs table renders SEPARATELY below this panel, on the shared table template.
 */
import { computed } from 'vue'

import HealthChip from '@/components/chips/HealthChip.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import {
  DB_AGE_WARN_AFTER_S,
  dbAgeSeconds,
  lastDataAt,
  silentFor,
  type FreshnessRow,
} from '@/system/freshness'

export interface ScanRunRow {
  scan_run_id: string
  scan_order: number
  images: number
  findings_total: number
  fixable_total: number
  /** per-run severity mix (M9d slice 2) — the committing scanner's own buckets, summed */
  severity?: Partial<Record<string, number>>
  started_at: string | null
  finished_at: string | null
}

export interface ProvenanceRow {
  scanner: string
  scanner_version?: string | null
  scanner_db_version?: string | null
  scanner_db_built?: string | null
  last_run?: { scan_run_id: string; scan_order: number; at: string | null } | null
  runs?: ScanRunRow[]
}

const props = defineProps<{
  scanner: string
  provenance: ProvenanceRow | null
  freshness: FreshnessRow | null
}>()

const fmt = (n: number) => n.toLocaleString('en-US')
const lastRun = () => props.provenance?.runs?.[0] ?? null

/** amber when the vuln DB the last committed run scanned with is older than the warn window */
const dbStale = computed(() => {
  const age = dbAgeSeconds(props.provenance?.scanner_db_built ?? null)
  return age !== null && age > DB_AGE_WARN_AFTER_S
})
const dbAgeLabel = computed(() =>
  silentFor(dbAgeSeconds(props.provenance?.scanner_db_built ?? null)),
)
</script>

<template>
  <div class="scan-card">
    <div class="scan-card-head">
      <ScannerTag :name="scanner" />
      <span v-if="provenance?.scanner_version" class="mono-cell scan-ver">v{{ provenance.scanner_version }}</span>
      <span class="scan-health"><HealthChip :rows="freshness ? [freshness] : []" /></span>
    </div>

    <p v-if="!provenance" class="scan-none">
      No committed run yet: this scanner has never reported for this cluster.
    </p>
    <template v-else>
      <div class="scan-stats">
        <div class="scan-stat">
          <span class="scan-num">{{ fmt(lastRun()?.images ?? 0) }}</span>
          <span class="scan-lbl">images · last run</span>
        </div>
        <div class="scan-stat">
          <span class="scan-num">{{ fmt(lastRun()?.findings_total ?? 0) }}</span>
          <span class="scan-lbl">findings · last run</span>
        </div>
        <div class="scan-stat">
          <span class="scan-num">{{ fmt(lastRun()?.fixable_total ?? 0) }}</span>
          <span class="scan-lbl">fixable · last run</span>
        </div>
        <div class="scan-stat">
          <span class="scan-num scan-num-sm" :title="freshness?.last_ingest_at ?? ''">{{
            lastDataAt(freshness?.last_ingest_at ?? null)
          }}</span>
          <span class="scan-lbl"
            >last ingest<template v-if="freshness?.silent_for_seconds != null">
              · {{ silentFor(freshness.silent_for_seconds) }} ago</template
            ></span
          >
        </div>
      </div>

      <div class="scan-meta">
        <span
          ><em>Vulnerability database</em>
          <span class="mono-cell">{{ provenance.scanner_db_version ?? '-' }}</span></span
        >
        <span
          ><em>Database built</em>
          <span class="mono-cell" :title="provenance.scanner_db_built ?? ''">{{
            lastDataAt(provenance.scanner_db_built ?? null)
          }}</span>
          <span
            v-if="dbStale"
            class="db-stale"
            title="A running scanner with a stale vulnerability database quietly under-reports. Refresh the published image"
            >· {{ dbAgeLabel }} old</span
          ></span
        >
        <span class="scan-gitops"
          >The version is set where the scanner runs, by its image tag. JAVV does not change it.</span
        >
      </div>
    </template>
  </div>
</template>

<style scoped>
/* prototype .scan-card family, on tokens */
.scan-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 16px;
}
.scan-card-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.scan-ver {
  font-size: var(--text-sm);
  color: var(--ink);
}
.scan-health {
  margin-left: auto;
}
.scan-none {
  margin: 14px 0 2px;
  font-size: var(--text-body);
  color: var(--soft);
}
.scan-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 16px 0 14px;
}
.scan-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
/* the head-stat grammar — stat numbers are mono/700 app-wide */
.scan-num {
  font-family: var(--font-mono);
  font-size: var(--text-stat);
  font-weight: 700;
  color: var(--ink);
}
.scan-num-sm {
  font-size: var(--text-card-title);
  padding-top: 5px;
}
/* labels follow the table-header ruling (2026-07-11): ink/700 — soft small caps read faint */
.scan-lbl {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--ink);
  text-transform: uppercase;
}
.scan-meta {
  display: flex;
  align-items: baseline;
  gap: 22px;
  border-top: 1px solid var(--line2);
  padding-top: 12px;
}
/* the provenance facts never wrap mid-label — the gitops note is the flexible one */
.scan-meta > span:not(.scan-gitops) {
  white-space: nowrap;
}
.scan-meta em {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ink);
  margin-right: 6px;
}
.scan-gitops {
  /* the one explanatory clause — stays soft (il-sub ruling) */
  margin-left: auto;
  font-size: var(--text-sm);
  color: var(--soft);
  text-align: right;
}
/* the history/staleness amber family — same register as the quiet-lens flag */
.db-stale {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--hist-fg);
}
</style>

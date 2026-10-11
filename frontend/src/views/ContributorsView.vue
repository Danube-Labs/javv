<script setup lang="ts">
/**
 * Contributors screen (M9d slice 3; SCREENS §11, prototype screens-heroes.jsx trimmed to
 * the wire's truth): the shared data-screen band (head-card + the handled-findings lens — the
 * same strip grammar every data screen carries) over team KPIs → podium → leaderboard, with
 * the recent-activity feed alongside. ALL numbers are `GET /contributors`' (leaderboard +
 * `totals`, one response — pooled team median/SLA are server-computed, never client math);
 * the feed is the M8c audit read. Scoped by the global trend window (`days`) and rewindable
 * (D28: the endpoint reconstructs at a past `as_of` — no limitation notice here). Trimmed by
 * ruling: per-actor severity mix / pace / streaks / roles (not on the wire), the scan-observed
 * trends chart (not attributable to contributors, A-m9). CSV export landed with issue 359 —
 * the button exports the SAME lens this screen reads, so the file cannot disagree with it.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { contributorsApiV1ContributorsGet } from '@/api/generated'
import type { ContributorsApiV1ContributorsGetData } from '@/api/generated'
import type { ActivityPoint } from '@/charts/buildAuditLensOption'
import ActivityFeed from '@/components/contributors/ActivityFeed.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import ContributorsLens from '@/components/contributors/ContributorsLens.vue'
import LeaderboardTable from '@/components/contributors/LeaderboardTable.vue'
import PodiumCard from '@/components/contributors/PodiumCard.vue'
import ProgressPanel from '@/components/contributors/ProgressPanel.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { useApi } from '@/composables/useApi'
import { useCsvExport } from '@/composables/useCsvExport'
import {
  daysFromWindow,
  fmtMedian,
  sortBoard,
  type BoardRow,
  type TeamTotals,
} from '@/contributors/viewModel'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'

const BOARD_CAP = 100 // the endpoint's terms-agg board size — the table labels the cap

const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const router = useRouter()

/** count cells → the audit rows they derive from (same provenance rule as the podium) */
function goAudit(action: string) {
  void router.push({ name: 'audit', query: { action } })
}
const { withGlobals } = useApi()

const board = ref<BoardRow[]>([])
const totals = ref<TeamTotals | null>(null)
const handledSeries = ref<ActivityPoint[]>([])
const failed = ref(false)
const settled = ref(false)

const query = computed(() =>
  clusterStore.selectedId
    ? withGlobals({ days: daysFromWindow(timeTravel.windowDays) })
    : null,
)

watch(
  query,
  async (q, old) => {
    if (!q) return
    if (old && old.cluster_id !== q.cluster_id) {
      settled.value = false
      board.value = []
      totals.value = null
      handledSeries.value = []
    }
    const response = await contributorsApiV1ContributorsGet({
      query: q as ContributorsApiV1ContributorsGetData['query'],
    })
    failed.value = !response.response?.ok || !response.data
    if (failed.value) {
      logger.warn('contributors_load_failed', { status: response.response?.status })
    } else {
      const body = response.data as unknown as {
        leaderboard: BoardRow[]
        handled_over_time: ActivityPoint[]
        totals: TeamTotals
      }
      board.value = body.leaderboard ?? []
      handledSeries.value = body.handled_over_time ?? []
      totals.value = body.totals ?? null
    }
    settled.value = true
  },
  { immediate: true, deep: true },
)

const podium = computed(() => {
  const top = sortBoard(board.value).slice(0, 3)
  // prototype visual order 2 · 1 · 3 — only when there are three to stage
  if (top.length === 3) return [
    { row: top[1]!, rank: 2 as const },
    { row: top[0]!, rank: 1 as const },
    { row: top[2]!, rank: 3 as const },
  ]
  return top.map((row, i) => ({ row, rank: (i + 1) as 1 | 2 | 3 }))
})

/* ---- Export CSV (prototype screen-head action): fetch → blob → download, so a 413/failed
 * response surfaces as a message rather than a broken tab (the AuditTrailView pattern). The
 * request carries `query` itself — the exact object the screen fetched with — so the file is
 * this window's leaderboard and not some other one ---- */
const toast = useToastStore()
const { exporting, run: runExport } = useCsvExport({
  path: '/api/v1/contributors/export.csv',
  filename: (stamp) => `javv-contributors-${stamp}.csv`,
  event: 'contributors_export_failed',
  onCapped: () => toast.info('Too many rows to export at once. Narrow the window first.'),
  onFailed: (status) =>
    toast.error(
      status
        ? `Export failed (${status}). Check the backend connection.`
        : 'Export failed. Check the backend connection.',
    ),
  onDone: (name) => toast.success(`Export downloaded · ${name}`),
})

async function exportCsv() {
  const q = query.value
  if (!q) return
  await runExport(q)
}

const fmt = (n: number) => n.toLocaleString('en-US')
const teamSla = computed(() =>
  totals.value?.sla_hit_pct == null ? '-' : `${Math.round(totals.value.sla_hit_pct)}%`,
)
const windowLabel = computed(() => timeTravel.windowLabel.toLowerCase())
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Contributors</h1>
        <p class="head-stat">
          <template v-if="!failed">{{ board.length }}</template
          ><span v-else class="muted-dash">-</span><span class="head-unit">
            contributor{{ board.length === 1 && !failed ? '' : 's' }}</span
          >
        </p>
        <p class="head-note">derived from the audit trail · triage actions, not scan deltas</p>
      </div>
      <ContributorsLens :series="handledSeries" :settled="settled" :failed="failed" />
    </div>

    <div v-if="!settled" class="contrib-skel" aria-busy="true" aria-label="Loading contributors">
      <UiSkeleton :height="92" />
      <UiSkeleton :height="320" />
    </div>

    <p v-else-if="failed" class="load-error" role="alert">
      Contributors unavailable. Check the backend connection.
    </p>

    <div v-else-if="board.length === 0" class="not-found" role="status">
      <p>No triage activity in this window. Handled findings chart contributors here.</p>
    </div>

    <template v-else>
      <!-- team KPI band: the ruled joined hairline-divided stat grammar (Overview), fed by
           the server's totals block — pooled median/SLA are not client-derivable -->
      <!-- count cells click through to the audit rows they were derived from (the podium
           provenance rule); median/SLA stay static — derived numbers, no row set IS them -->
      <div v-if="totals" class="stat-band stat-band--stat">
        <button class="stat-cell" title="Open resolve actions in the audit log" @click="goAudit('resolve')">
          <span class="stat-label"><i class="stat-dot" style="background: var(--state-resolved-solid)" />resolved<AppIcon class="cell-go" name="chevron" :size="11" /></span>
          <span class="stat-num">{{ fmt(totals.by_action['resolve'] ?? 0) }}</span>
          <span class="stat-sub">{{ windowLabel }}</span>
        </button>
        <button class="stat-cell" title="Open acknowledge actions in the audit log" @click="goAudit('acknowledge')">
          <span class="stat-label"><i class="stat-dot" style="background: var(--state-ack-solid)" />acknowledged<AppIcon class="cell-go" name="chevron" :size="11" /></span>
          <span class="stat-num">{{ fmt(totals.by_action['acknowledge'] ?? 0) }}</span>
          <span class="stat-sub">{{ windowLabel }}</span>
        </button>
        <div class="stat-cell">
          <span class="stat-label"><i class="stat-dot" style="background: var(--teal)" />median time-to-resolve</span>
          <span class="stat-num">{{ fmtMedian(totals.median_ttr_seconds) }}</span>
          <span class="stat-sub">pooled across the team</span>
        </div>
        <div class="stat-cell">
          <span class="stat-label"><i class="stat-dot" style="background: var(--coral)" />SLA met</span>
          <span class="stat-num">{{ teamSla }}</span>
          <span class="stat-sub">of SLA-bearing handled findings</span>
        </div>
        <button class="stat-cell" title="Open resolve actions in the audit log: all severities. This count is criticals only" @click="goAudit('resolve')">
          <span class="stat-label"><i class="stat-dot" style="background: var(--sev-critical-solid)" />critical cleared<AppIcon class="cell-go" name="chevron" :size="11" /></span>
          <span class="stat-num">{{ fmt(totals.critical_cleared) }}</span>
          <span class="stat-sub">{{ windowLabel }}</span>
        </button>
      </div>

      <div class="contrib-layout">
        <div class="contrib-main">
          <section class="card-section">
            <div class="card-head">
              <h2>Top contributors</h2>
              <p class="card-sub">most findings resolved · {{ windowLabel }}</p>
            </div>
            <div class="podiums" :class="{ 'podiums-full': podium.length === 3 }">
              <PodiumCard v-for="p in podium" :key="p.row.actor" :row="p.row" :rank="p.rank" />
            </div>
          </section>

          <section class="card-section card-flush">
            <div class="card-head">
              <h2>Leaderboard</h2>
              <p class="card-sub">all contributors · ranked by resolved</p>
              <UiButton
                class="card-action"
                variant="control"
                :disabled="exporting || board.length === 0"
                @click="exportCsv"
              >
                <AppIcon name="download" :size="13" />{{
                  exporting ? 'Exporting…' : 'Export leaderboard (CSV)'
                }}
              </UiButton>
            </div>
            <LeaderboardTable :rows="board" :cap="BOARD_CAP" />
          </section>
        </div>

        <div class="contrib-side">
          <section class="card-section">
            <div class="card-head">
              <h2>Triage progress</h2>
              <p class="card-sub">triaged vs open · current state, not the trend window</p>
            </div>
            <ProgressPanel :query="query" />
          </section>

          <section class="card-section">
            <div class="card-head">
              <h2>Recent activity</h2>
              <p class="card-sub">from the audit trail</p>
            </div>
            <ActivityFeed :query="query" />
          </section>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* band/head scaffolding lives in base.css (shared data-screen grammar) */
/* the card head is baseline-aligned for its title+sub pair; a control has no useful baseline,
   so it centers itself and takes the row's slack to sit at the right edge */
.card-action {
  margin-left: auto;
  align-self: center;
  /* the kit's default --line border is near-invisible on a white card, which left this
     reading as a label rather than a control directly above the dark table header
     (operator ruling 2026-07-30 on built specimens) */
  border-color: var(--slate2);
}
/* the kit's hover line (--control-hover-line) is a LIGHTER beige, tuned against that default
   border — inherited here it made the button weaken on hover. Keep the kit's wash, step the
   border darker instead, so both hover signals point the same way */
.card-action:hover:not(:disabled),
.card-action:active:not(:disabled) {
  border-color: var(--slate);
}
.contrib-layout {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 14px;
  align-items: start;
  margin-top: 14px;
}
.contrib-main,
.contrib-side {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
@media (width <= 1100px) {
  .contrib-layout {
    grid-template-columns: 1fr;
  }
}

/* section cards — the scan-card surface grammar */
.card-section {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 14px 16px;
}
.card-flush {
  padding: 14px 0 0;
}
.card-flush .card-head {
  padding: 0 16px;
}
.card-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;
}
.card-head h2 {
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
}
.card-sub {
  margin: 0;
  font-size: var(--text-control);
  color: var(--soft);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* prototype .podiums grid — 2·1·3 staging only with a full podium; a short roster keeps
   card-sized columns instead of one contributor stretching the whole stage */
.podiums {
  display: grid;
  gap: 12px;
  align-items: end;
  grid-template-columns: repeat(auto-fit, minmax(140px, 240px));
  justify-content: center;
  padding-top: 12px;
}
.podiums-full {
  grid-template-columns: 1fr 1.12fr 1fr;
}

/* the ruled KPI band grammar (Overview/finding-detail risk band), static cells */
/* the joined stat-band SKIN lives in base.css (issue 368; this screen = the --stat register)
   — only this screen's layout here */
.stat-band {
  grid-template-columns: repeat(5, 1fr);
}
@media (width <= 1100px) {
  .stat-band {
    grid-template-columns: repeat(3, 1fr);
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
.contrib-skel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
</style>

<script setup lang="ts">
/**
 * The ingest lens — a discover-style strip in the screen head: committed scan runs
 * per day over the global time range, per scanner (never merged), plus WHEN data last
 * arrived. It exists to answer "why does the table still show findings when the scanners
 * are idle?" — the table shows state at the END of the range (D28); this strip shows the
 * ingest moments inside it. Clicking a day rewinds the whole app to the end of that day
 * (the state after its ingests committed); a still-running day is "now". Drop it in the
 * `.screen-head` of any cluster-scoped screen.
 *
 * Every number is a server aggregation: `GET /trends/scans` (cardinality-deduped committed
 * runs) + `GET /scanners/freshness`. The freshness line is NOW-truth, so it hides at a
 * past T — there the range copy alone carries the message.
 */
import { computed, ref, watch } from 'vue'

import { client } from '@/api/client'
import {
  scannerFreshnessApiV1ScannersFreshnessGet,
  scansTrendApiV1TrendsScansGet,
} from '@/api/generated'
import {
  buildIngestLensOption,
  ingestInterval,
  ingestLensDates,
} from '@/charts/buildIngestLensOption'
import type { ScanActivityData } from '@/charts/buildScanActivityOption'
import { buildTrendQuery, isSubDayWindow } from '@/charts/buildTrendQuery'
import GuideLink from '@/components/about/GuideLink.vue'
import EChart from '@/components/charts/EChart.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBucketRewind } from '@/composables/useBucketRewind'
import { logger } from '@/lib/logger'
import { lastDataAt, silentFor, type FreshnessRow } from '@/system/freshness'
import { useTimeTravelStore } from '@/stores/timeTravel'

const props = withDefaults(
  defineProps<{
    clusterId: string
    /** What the D28 clause points at — "the table" on grid screens, "this screen" on overview. */
    subject?: string
  }>(),
  { subject: 'the table' },
)
const timeTravel = useTimeTravelStore()

const series = ref<ScanActivityData>({})
const freshness = ref<FreshnessRow[]>([])
const freshnessFailed = ref(false)
const failed = ref(false)
// no claim before evidence: quiet/failed/chart render only once a response has LANDED —
// the pre-data default used to satisfy `quiet` and flash the amber panel on every load
const settled = ref(false)

watch(
  () => [props.clusterId, timeTravel.t, timeTravel.windowDays] as const,
  async ([id, t, days], old) => {
    if (!id) return
    // a cluster switch invalidates what's on screen (another tenant's chart would be a lie);
    // a T/window change on the same cluster keeps the current chart until the new one lands
    if (old && old[0] !== id) {
      settled.value = false
      series.value = {}
      freshness.value = []
    }
    const [scans, fresh] = await Promise.all([
      scansTrendApiV1TrendsScansGet({
        client,
        query: { ...buildTrendQuery(id, days, t), interval: ingestInterval(days, t) } as never,
      }),
      scannerFreshnessApiV1ScannersFreshnessGet({ client, query: { cluster_id: id } }),
    ])
    failed.value = !scans.response?.ok || !scans.data
    if (failed.value) logger.warn('ingest_lens_failed', { status: scans.response?.status })
    series.value = failed.value ? {} : ((scans.data as { series: ScanActivityData }).series ?? {})
    // a refused freshness read drops the old time: it belonged to an earlier read (issue 833, F5)
    freshnessFailed.value = !fresh.response?.ok || !fresh.data
    freshness.value = freshnessFailed.value
      ? []
      : ((fresh.data as { scanners: FreshnessRow[] }).scanners ?? [])
    if (freshnessFailed.value) logger.warn('ingest_lens_freshness_failed', { status: fresh.response?.status })
    settled.value = true
  },
  { immediate: true },
)

const totalRuns = computed(() =>
  Object.values(series.value).reduce(
    (n, rows) => n + (rows ?? []).reduce((m, p) => m + p.scans, 0),
    0,
  ),
)
const latest = computed(
  () =>
    freshness.value
      .filter((r) => r.last_ingest_at !== null)
      .sort((a, b) => (a.last_ingest_at! < b.last_ingest_at! ? 1 : -1))[0] ?? null,
)
const interval = computed(() => ingestInterval(timeTravel.windowDays, timeTravel.t))
const option = computed(() => buildIngestLensOption(series.value, interval.value))
// daily bars only mislead when the range is sub-day AND the buckets stayed daily (past T)
const subDay = computed(() => interval.value === 'day' && isSubDayWindow(timeTravel.windowDays))
/** Quiet range = the one state worth a visual flag (operator 2026-07-11): the amber wash
 * only when NOTHING was committed in the range — data present stays a plain card. */
const quiet = computed(() => settled.value && !failed.value && totalRuns.value === 0)

const rewindToBucket = useBucketRewind()
function onPointClick(params: { dataIndex: number }) {
  rewindToBucket(ingestLensDates(series.value)[params.dataIndex], interval.value)
}
</script>

<template>
  <section class="ingest-lens" :class="{ 'il-quiet': quiet }" aria-label="Scan ingest activity">
    <div class="il-head">
      <h2 class="il-title">Scan ingest</h2>
      <span class="il-sub"
        >runs per {{ interval }} · {{ timeTravel.windowLabel.toLowerCase()
        }}<template v-if="subDay"> (daily bars: covers the last 1 day)</template> ·
        {{ subject }} shows the state at the <b>end</b> of this range</span
      >
      <GuideLink class="il-help" section="time-range" variant="popover" />
      <span v-if="timeTravel.isNow && latest" class="il-last mono-cell">
        last ingest {{ latest.scanner }} · {{ lastDataAt(latest.last_ingest_at) }} ({{
          silentFor(latest.silent_for_seconds)
        }} ago)
      </span>
      <span v-else-if="timeTravel.isNow && freshnessFailed" class="il-last mono-cell">last ingest -</span>
    </div>
    <!-- pre-data: a shimmer where the chart will be — never the amber claim (a quiet range is an
         ANSWER; before the response lands there is none) -->
    <UiSkeleton v-if="!settled" :height="84" radius="sm" label="Loading ingest activity" class="skel-gap" />
    <p v-else-if="failed" class="il-empty">Ingest activity unavailable.</p>
    <p v-else-if="totalRuns === 0" class="il-empty">
      No scans committed in this range<template v-if="timeTravel.isNow && latest"
        >: {{ subject }} shows the state last updated {{ lastDataAt(latest.last_ingest_at) }},
        {{ silentFor(latest.silent_for_seconds) }} ago</template
      >.
    </p>
    <div v-else title="Click a day to view the whole app as of the end of that day">
      <EChart :option="option" :height="84" @point-click="onPointClick" />
    </div>
  </section>
</template>

<style scoped>
.ingest-lens {
  /* fills the screen-head-band's table track — flush with the grid edges below */
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 10px 14px 4px;
}
/* the quiet-range flag: the history/staleness amber — attention ONLY when the range holds
   no commits and the table is older than it looks (operator ruling) */
.il-quiet {
  background: var(--hist-bg);
  border-color: var(--hist-line);
}
.il-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}
.il-title {
  flex: none;
  white-space: nowrap;
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
}
/* one size, ink-dark (operator: the small soft text was unreadable) — only the explanatory
   clause stays soft */
/* when the head runs out of room the explanation wraps onto a second line: cut short, it ended
   at "the state at the…", which says nothing (issue 681) */
.il-sub {
  flex: 1 1 0;
  min-width: 12ch;
  font-size: var(--text-control);
  color: var(--ink);
}
.il-sub b {
  font-weight: 700;
  color: var(--ink);
}
.il-help {
  flex: none;
  align-self: center;
}
.il-last {
  margin-left: auto;
  font-size: var(--text-control);
  color: var(--ink);
  text-align: right;
}
/* warning-grade copy reads at body size, never fine print (operator ruling) */
.il-empty {
  margin: auto 0;
  padding-bottom: 6px;
  font-size: var(--text-body);
  font-weight: 500;
  color: var(--ink);
}
.skel-gap {
  margin-bottom: 6px;
}
</style>

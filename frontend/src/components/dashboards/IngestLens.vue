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
 *
 * `filters` is the filter query of the screen (issue 1293). The strip sends the filters that a
 * scan record holds (`scanFilters`) and says so when the screen has another filter on.
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
  onAxis,
  stripAxis,
} from '@/charts/buildIngestLensOption'
import type { ScanActivityData } from '@/charts/buildScanActivityOption'
import { buildTrendQuery, isSubDayWindow } from '@/charts/buildTrendQuery'
import GuideLink from '@/components/about/GuideLink.vue'
import EChart from '@/components/charts/EChart.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBucketRewind } from '@/composables/useBucketRewind'
import { useStripNow } from '@/composables/useStripNow'
import { scanFilters } from '@/dashboards/scanFilters'
import { logger } from '@/lib/logger'
import { lastDataAt, silentFor, type FreshnessRow } from '@/system/freshness'
import { useTimeTravelStore } from '@/stores/timeTravel'

const props = withDefaults(
  defineProps<{
    clusterId: string
    /** What the D28 clause points at — "the table" on grid screens, "this screen" on overview. */
    subject?: string
    /** the filter query of the screen; none on a screen without table filters */
    filters?: Record<string, unknown>
  }>(),
  { subject: 'the table', filters: () => ({}) },
)
const timeTravel = useTimeTravelStore()
/** the subject starts a sentence in the strip text */
const subjectCap = computed(() => props.subject.charAt(0).toUpperCase() + props.subject.slice(1))

const series = ref<ScanActivityData>({})
const freshness = ref<FreshnessRow[]>([])
const freshnessFailed = ref(false)
const failed = ref(false)
/** the route refused the filters of the screen (422): a value past its cap, or a pair that it
 * refuses, as Tag with No tag. Not a connection fault. */
const refused = ref(false)
// no claim before evidence: quiet/failed/chart render only once a response has LANDED —
// the pre-data default used to satisfy `quiet` and flash the amber panel on every load
const settled = ref(false)

const split = computed(() => scanFilters(props.filters))
/** the screen has a filter on that a scan record does not hold */
const otherFilters = computed(() => split.value.ignored.length > 0)
/** a scan filter applies: the last scan of `/scanners/freshness` is the last scan of the whole
 * cluster, so the strip does not read or show it (operator decision Q2 B, issue 1293) */
const scanFiltered = computed(() => Object.keys(split.value.applied).length > 0)

let seq = 0
// one source for each value, and the filters as text: a host that passes an equal new object on
// each render does not read again (a getter of one array is compared as a whole, by identity)
watch(
  [() => props.clusterId, () => timeTravel.t, () => timeTravel.windowDays, () => JSON.stringify(split.value.applied)],
  async ([id, t, days], old) => {
    if (!id) return
    // a cluster switch invalidates what's on screen (another tenant's chart would be a lie);
    // a T/window change on the same cluster keeps the current chart until the new one lands
    if (old && old[0] !== id) {
      settled.value = false
      series.value = {}
      freshness.value = []
    }
    const mine = ++seq
    const withFreshness = !scanFiltered.value
    const [scans, fresh] = await Promise.all([
      scansTrendApiV1TrendsScansGet({
        client,
        query: { ...split.value.applied, ...buildTrendQuery(id, days, t), interval: ingestInterval(days, t) } as never,
      }),
      withFreshness ? scannerFreshnessApiV1ScannersFreshnessGet({ client, query: { cluster_id: id } }) : null,
    ])
    if (mine !== seq) return // a newer read owns the strip now
    failed.value = !scans.response?.ok || !scans.data
    refused.value = failed.value && scans.response?.status === 422
    if (failed.value) logger.warn('ingest_lens_failed', { status: scans.response?.status })
    series.value = failed.value ? {} : ((scans.data as { series: ScanActivityData }).series ?? {})
    // a refused freshness read drops the old time: it belonged to an earlier read (issue 833, F5)
    freshnessFailed.value = fresh !== null && (!fresh.response?.ok || !fresh.data)
    freshness.value =
      fresh === null || freshnessFailed.value ? [] : ((fresh.data as { scanners: FreshnessRow[] }).scanners ?? [])
    if (freshnessFailed.value) logger.warn('ingest_lens_freshness_failed', { status: fresh?.response?.status })
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
// the band's clock, shared with the other strips (issue 1292)
const stripNow = useStripNow()
// each count at its date of the range's axis: the strips of a band line up (issue 1292)
const shown = computed(() =>
  onAxis(series.value, stripAxis(timeTravel.windowDays, timeTravel.t, interval.value, stripNow.value)),
)
const option = computed(() => buildIngestLensOption(shown.value, interval.value, 'images scanned'))
// daily bars only mislead when the range is sub-day AND the buckets stayed daily (past T)
const subDay = computed(() => interval.value === 'day' && isSubDayWindow(timeTravel.windowDays))
/** Quiet range = the one state worth a visual flag (operator 2026-07-11): the amber wash
 * only when NOTHING was committed in the range — data present stays a plain card. */
const quiet = computed(() => settled.value && !failed.value && totalRuns.value === 0)

const rewindToBucket = useBucketRewind()
function onPointClick(params: { dataIndex: number }) {
  rewindToBucket(ingestLensDates(shown.value)[params.dataIndex], interval.value)
}
</script>

<template>
  <section class="ingest-lens" :class="{ 'il-quiet': quiet }" aria-label="Scan ingest activity">
    <div class="il-head">
      <h2 class="il-title">Scan ingest</h2>
      <span class="il-sub"
        >Scans for each {{ interval }} · {{ timeTravel.windowLabel.toLowerCase()
        }}<template v-if="subDay">. The chart has one bar for each day. It shows all of the last day</template>.
        {{ subjectCap }} shows the state at the <b>end</b> of this range.<template v-if="otherFilters">
          Only the namespace, image, tag, digest and scanner filters apply.</template></span
      >
      <GuideLink class="il-help" section="time-range" variant="popover" />
      <span v-if="timeTravel.isNow && !scanFiltered && latest" class="il-last mono-cell">
        last scan {{ latest.scanner }} · {{ lastDataAt(latest.last_ingest_at) }} ({{
          silentFor(latest.silent_for_seconds)
        }} ago)
      </span>
      <span v-else-if="timeTravel.isNow && !scanFiltered && freshnessFailed" class="il-last mono-cell">last scan -</span>
    </div>
    <!-- pre-data: a shimmer where the chart will be — never the amber claim (a quiet range is an
         ANSWER; before the response lands there is none) -->
    <UiSkeleton v-if="!settled" :height="84" radius="sm" label="Loading the scans" class="skel-gap" />
    <p v-else-if="refused" class="il-empty">JAVV cannot count the scans with these filters.</p>
    <p v-else-if="failed" class="il-empty">JAVV cannot show the scans. Check the backend connection.</p>
    <p v-else-if="totalRuns === 0" class="il-empty">
      No scans in this range. <template v-if="timeTravel.isNow && !scanFiltered && latest"
        >{{ subjectCap }} shows the state of the last scan, {{ lastDataAt(latest.last_ingest_at) }},
        {{ silentFor(latest.silent_for_seconds) }} ago.</template
      >
    </p>
    <div v-else title="Select a day to see the app as it was at the end of that day">
      <EChart :option="option" :height="84" @point-click="onPointClick" />
    </div>
  </section>
</template>

<style scoped>
/* the shared strip rules are in base.css (issue 1197) */
.ingest-lens {
  /* fills the screen-head-band's table track — flush with the grid edges below */
  flex: 1 1 auto;
}
.il-title {
  flex: none;
  white-space: nowrap;
}
/* when the head runs out of room the explanation wraps onto a second line: cut short, it ended
   at "the state at the…", which says nothing (issue 681) */
.il-sub {
  flex: 1 1 0;
  min-width: 12ch;
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
</style>

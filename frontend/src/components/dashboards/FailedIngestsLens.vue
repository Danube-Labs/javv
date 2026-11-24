<script setup lang="ts">
/**
 * The failed-ingests lens: pushes the backend refused after checking their token, per bucket,
 * one bar series per scanner (never merged) — `GET /trends/ingest-failures`. Built to sit under
 * the Scan ingest strip on the same axis: the same window, the same day/hour bucket rule, so a day
 * lines up across both. Its own scale on purpose: runs peak in the hundreds while refusals are a
 * handful, so bars sharing Scan ingest's axis would vanish (issue 575).
 *
 * Self-contained per DESIGN.md section 10 — `(clusterId, t, windowDays)` in, its own fetch and
 * loading/empty/error states. A click on a day rewinds the whole app, like Scan ingest.
 */
import { computed, ref, watch } from 'vue'

import { client } from '@/api/client'
import { ingestFailuresTrendApiV1TrendsIngestFailuresGet } from '@/api/generated'
import {
  buildIngestLensOption,
  ingestInterval,
  ingestLensDates,
  onAxis,
  stripAxis,
} from '@/charts/buildIngestLensOption'
import { buildTrendQuery } from '@/charts/buildTrendQuery'
import EChart from '@/components/charts/EChart.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBucketRewind } from '@/composables/useBucketRewind'
import { useStripNow } from '@/composables/useStripNow'
import { logger } from '@/lib/logger'
import {
  failuresAsLensSeries,
  totalRefused,
  type IngestFailuresTrend,
} from '@/system/ingestFailures'

const props = defineProps<{
  clusterId: string
  /** the rewound T, `null` = now */
  t: string | null
  windowDays: number
}>()

const series = ref<IngestFailuresTrend>({})
const failed = ref(false)
// no claim before evidence: "no refused pushes" only once an answer has landed
const settled = ref(false)

const interval = computed(() => ingestInterval(props.windowDays, props.t))

watch(
  () => [props.clusterId, props.t, props.windowDays] as const,
  async ([id, t, days], old) => {
    if (old && old[0] !== id) {
      settled.value = false // another tenant's bars would be a lie
      series.value = {}
    }
    const { data, response } = await ingestFailuresTrendApiV1TrendsIngestFailuresGet({
      client,
      query: { ...buildTrendQuery(id, days, t), interval: interval.value } as never,
    })
    failed.value = !response?.ok || !data
    if (failed.value) logger.warn('failed_ingests_lens_failed', { status: response?.status })
    series.value = failed.value ? {} : ((data as { series: IngestFailuresTrend }).series ?? {})
    settled.value = true
  },
  { immediate: true },
)

// the band's clock, shared with the other strips (issue 1292)
const stripNow = useStripNow()
// each count at its date of the range's axis: the strips of a band line up (issue 1292)
const lensSeries = computed(() =>
  onAxis(failuresAsLensSeries(series.value), stripAxis(props.windowDays, props.t, interval.value, stripNow.value)),
)
const refused = computed(() => totalRefused(series.value))
const option = computed(() => buildIngestLensOption(lensSeries.value, interval.value, 'refused scans'))

const rewindToBucket = useBucketRewind()
function onPointClick(params: { dataIndex: number }) {
  rewindToBucket(ingestLensDates(lensSeries.value)[params.dataIndex], interval.value)
}
</script>

<template>
  <section class="ingest-lens" aria-label="Failed ingest activity">
    <div class="il-head">
      <h2 class="il-title">Failed ingests</h2>
      <span class="il-sub">The scans that the backend refused, for each {{ interval }}.</span>
      <span v-if="settled && !failed && refused > 0" class="fl-total mono-cell"
        >{{ refused }} in this range</span
      >
    </div>
    <UiSkeleton v-if="!settled" :height="56" radius="sm" label="Loading the refused scans" class="skel-gap" />
    <p v-else-if="failed" class="il-empty">JAVV cannot show the refused scans. Check the backend connection.</p>
    <p v-else-if="refused === 0" class="il-empty">No refused scans in this range.</p>
    <div v-else title="Select a day to see the app as it was at the end of that day">
      <EChart :option="option" :height="56" @point-click="onPointClick" />
    </div>
  </section>
</template>

<style scoped>
/* the shared strip rules are in base.css (issue 1197). This strip does not grow in its row. */
.il-sub {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fl-total {
  margin-left: auto;
  font-size: var(--text-control);
  color: var(--ink);
}
</style>

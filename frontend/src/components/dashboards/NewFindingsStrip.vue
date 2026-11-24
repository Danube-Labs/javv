<script setup lang="ts">
/**
 * The New findings strip (issue 1292): the findings first seen in each bucket, by severity, under
 * the filters of the screen — `GET /trends/new-findings`. It sits under Scan ingest in one band,
 * with the same range and the same day or hour rule. Each count sits at its date of the range's
 * axis (`stripAxis`), so a day or an hour lines up across the two strips. Its own scale: a new
 * build brings hundreds of findings on one day, and most days bring none.
 *
 * Self-contained per DESIGN.md section 10: `(clusterId, t, windowDays, filters)` in, its own read
 * and its own loading, empty and error states. `filters` is the filter query of the screen. The
 * strip drops its globals, and "New in range": the strip counts the findings first seen in its
 * range already, and a past time refuses that filter.
 */
import { computed, ref, watch } from 'vue'

import { client } from '@/api/client'
import { newFindingsTrendApiV1TrendsNewFindingsGet } from '@/api/generated'
import { ingestInterval, stripAxis } from '@/charts/buildIngestLensOption'
import {
  buildNewFindingsStripOption,
  totalNew,
  type NewFindingsSeries,
} from '@/charts/buildNewFindingsStripOption'
import { buildTrendQuery } from '@/charts/buildTrendQuery'
import EChart from '@/components/charts/EChart.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBucketRewind } from '@/composables/useBucketRewind'
import { logger } from '@/lib/logger'

const props = defineProps<{
  clusterId: string
  /** the rewound T, `null` = now */
  t: string | null
  windowDays: number
  /** the filter query of the screen */
  filters: Record<string, unknown>
  /** a sentence after the line of the strip, for example the filters that apply on a screen */
  note?: string
}>()

const series = ref<NewFindingsSeries>({})
const failed = ref(false)
/** a past time refuses a filter of the screen (422): not a connection fault */
const refused = ref(false)
// no claim before evidence: "no new findings" only once an answer has landed
const settled = ref(false)

const interval = computed(() => ingestInterval(props.windowDays, props.t))
// the globals of the screen query and "New in range" are the strip's own range
const OWN_KEYS = new Set(['cluster_id', 'as_of', 'new_within_days'])
const filterParams = computed(() =>
  Object.fromEntries(Object.entries(props.filters).filter(([key]) => !OWN_KEYS.has(key))),
)

let seq = 0
watch(
  () => [props.clusterId, props.t, props.windowDays, JSON.stringify(filterParams.value)] as const,
  async ([id, t, days], old) => {
    if (old && old[0] !== id) {
      settled.value = false // another tenant's bars would be a lie
      series.value = {}
    }
    const mine = ++seq
    const { data, response } = await newFindingsTrendApiV1TrendsNewFindingsGet({
      client,
      query: { ...filterParams.value, ...buildTrendQuery(id, days, t), interval: interval.value } as never,
    })
    if (mine !== seq) return // a newer read owns the strip now
    failed.value = !response?.ok || !data
    refused.value = failed.value && response?.status === 422 && t !== null
    if (failed.value) logger.warn('new_findings_strip_failed', { status: response?.status })
    series.value = failed.value ? {} : ((data as { series: NewFindingsSeries }).series ?? {})
    settled.value = true
  },
  { immediate: true },
)

const axis = computed(() => stripAxis(props.windowDays, props.t, interval.value))
const total = computed(() => totalNew(series.value))
const option = computed(() => buildNewFindingsStripOption(series.value, axis.value, interval.value))

const rewindToBucket = useBucketRewind()
function onPointClick(params: { dataIndex: number }) {
  rewindToBucket(axis.value[params.dataIndex], interval.value)
}
</script>

<template>
  <section class="ingest-lens" aria-label="New findings">
    <div class="il-head">
      <h2 class="il-title">New findings</h2>
      <span class="il-sub">The findings first seen in each {{ interval }}, by severity.{{ note ? ` ${note}` : '' }}</span>
      <span v-if="settled && !failed && total > 0" class="nf-total mono-cell">{{ total }} in this range</span>
    </div>
    <UiSkeleton v-if="!settled" :height="56" radius="sm" label="Loading the new findings" class="skel-gap" />
    <p v-else-if="refused" class="il-empty">JAVV cannot count the new findings with these filters at a past time.</p>
    <p v-else-if="failed" class="il-empty">JAVV cannot show the new findings. Check the backend connection.</p>
    <p v-else-if="total === 0" class="il-empty">No new findings in this range.</p>
    <div v-else title="Select a day to see the app as it was at the end of that day">
      <EChart :option="option" :height="56" @point-click="onPointClick" />
    </div>
  </section>
</template>

<style scoped>
/* the shared strip rules are in base.css (issue 1197) */
.il-sub {
  flex: 1 1 0;
  min-width: 12ch;
}
.nf-total {
  margin-left: auto;
  font-size: var(--text-control);
  color: var(--ink);
}
</style>

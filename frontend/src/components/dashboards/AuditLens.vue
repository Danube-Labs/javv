<script setup lang="ts">
/**
 * The audit lens — the ingest lens's strip grammar pointed at the journal (operator ask,
 * M9d): journaled events per bucket over the global time range, UNDER the screen's current
 * filters, so the histogram always describes the table below it (the discover-strip contract).
 * Every number is the server's (`GET /audit/facets` `activity` date_histogram); clicking a
 * bucket rewinds the whole app to that bucket's end (D28), same as the ingest lens.
 */
import { computed, ref, watch } from 'vue'

import { auditFacetsApiV1AuditFacetsGet } from '@/api/generated'
import { buildAuditLensOption, type ActivityPoint } from '@/charts/buildAuditLensOption'
import { ingestInterval } from '@/charts/buildIngestLensOption'
import EChart from '@/components/charts/EChart.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useBucketRewind } from '@/composables/useBucketRewind'
import { logger } from '@/lib/logger'
import { useTimeTravelStore } from '@/stores/timeTravel'

const props = withDefaults(
  defineProps<{
    /** the screen's full filter query (cluster_id + as_of + term filters) — the lens counts
     * exactly what the table shows */
    query: Record<string, unknown> | null
    /** strip heading — screens pointing the lens at a SLICE of the journal (e.g. Approvals →
     * decision activity) rename it so the copy stays accurate about what is counted */
    title?: string
    sub?: string
    /** the quiet-range copy; a host with no table under the strip says so without the table */
    emptyNote?: string
  }>(),
  {
    title: 'Audit activity',
    sub: '',
    emptyNote: 'No journaled activity in this range. Older events are still in the table below.',
  },
)
const timeTravel = useTimeTravelStore()

const rows = ref<ActivityPoint[]>([])
const failed = ref(false)
// no claim before evidence: quiet/failed/chart render only once a response has LANDED —
// the pre-data default used to satisfy `quiet` and flash the amber panel on every load
const settled = ref(false)

const interval = computed(() => ingestInterval(timeTravel.windowDays, timeTravel.t))

watch(
  () => [props.query, timeTravel.windowDays] as const,
  async ([q, days], old) => {
    if (!q) return
    // a cluster switch invalidates what's on screen; filter/T/window changes on the same
    // cluster keep the current chart until the new one lands
    if (old?.[0] && old[0].cluster_id !== q.cluster_id) {
      settled.value = false
      rows.value = []
    }
    const response = await auditFacetsApiV1AuditFacetsGet({
      query: {
        ...q,
        interval: interval.value,
        window_days: Math.min(365, Math.max(1, Math.ceil(days))),
      } as never,
    })
    failed.value = !response.response?.ok || !response.data
    if (failed.value) {
      logger.warn('audit_lens_failed', { status: response.response?.status })
      rows.value = []
    } else {
      rows.value = ((response.data as { activity?: ActivityPoint[] }).activity ?? [])
    }
    settled.value = true
  },
  { immediate: true, deep: true },
)

const totalEvents = computed(() => rows.value.reduce((n, p) => n + p.count, 0))
const option = computed(() => buildAuditLensOption(rows.value, interval.value))
const quiet = computed(() => settled.value && !failed.value && totalEvents.value === 0)

const rewindToBucket = useBucketRewind()
function onPointClick(params: { dataIndex: number }) {
  rewindToBucket(rows.value[params.dataIndex]?.date, interval.value)
}
</script>

<template>
  <section class="ingest-lens" :class="{ 'il-quiet': quiet }" :aria-label="props.title">
    <div class="il-head">
      <h2 class="il-title">{{ props.title }}</h2>
      <span v-if="props.sub" class="il-sub">{{ props.sub }}</span>
      <span v-else class="il-sub"
        >events per {{ interval }} · {{ timeTravel.windowLabel.toLowerCase() }} · under the
        current filters · the table lists <b>all</b> events up to the range end</span
      >
    </div>
    <!-- pre-data: a shimmer where the chart will be — never the amber claim (a quiet range is an
         ANSWER; before the response lands there is none) -->
    <UiSkeleton v-if="!settled" :height="84" radius="sm" label="Loading audit activity" class="skel-gap" />
    <p v-else-if="failed" class="il-empty">Audit activity unavailable.</p>
    <p v-else-if="totalEvents === 0" class="il-empty">{{ props.emptyNote }}</p>
    <div v-else title="Click a bucket to view the whole app as of its end">
      <EChart :option="option" :height="84" @point-click="onPointClick" />
    </div>
  </section>
</template>

<style scoped>
/* the shared strip rules are in base.css (issue 1197) */
.ingest-lens {
  flex: 1 1 auto;
}
.il-sub {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.il-empty {
  margin: auto 0;
  font-weight: 500;
}
</style>

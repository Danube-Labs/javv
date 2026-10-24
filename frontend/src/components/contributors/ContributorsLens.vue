<script setup lang="ts">
/**
 * The contributors lens — the shared strip grammar pointed at HANDLED findings (M9d slice 3):
 * the `/contributors` read's own `handled_over_time` daily histogram (settling actions:
 * resolve / not affected / risk accept / acknowledge), so the strip and the board below can
 * never disagree — one response, no second fetch. Props-fed there; the view owns the settled
 * contract (lens ruling, issue 355: no claim before evidence). On a dashboard there is no
 * board, so the lens gets only `query` and reads the same route itself. Clicking a bucket
 * rewinds the whole app to that bucket's end (D28), same as every lens.
 */
import { computed, ref, watch } from 'vue'

import { contributorsApiV1ContributorsGet } from '@/api/generated'
import type { ContributorsApiV1ContributorsGetData } from '@/api/generated'
import { buildAuditLensOption, type ActivityPoint } from '@/charts/buildAuditLensOption'
import { bucketEndT } from '@/charts/buildIngestLensOption'
import EChart from '@/components/charts/EChart.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { lastDataAt } from '@/system/freshness'

const props = defineProps<{
  /** the Contributors read's own series; without it the lens reads `query` itself */
  series?: ActivityPoint[]
  settled?: boolean
  failed?: boolean
  /** the contributors query (cluster_id, as_of, days) of a lens with no board under it */
  query?: Record<string, unknown> | null
}>()
const timeTravel = useTimeTravelStore()

const fed = computed(() => props.series !== undefined)
const ownSeries = ref<ActivityPoint[]>([])
const ownFailed = ref(false)
const ownSettled = ref(false)

let seq = 0
watch(
  () => (fed.value ? null : props.query),
  async (q, old) => {
    if (!q) return
    const mine = ++seq
    if (old && old.cluster_id !== q.cluster_id) {
      ownSettled.value = false // another tenant's chart would be a lie
      ownSeries.value = []
    }
    const { data, response } = await contributorsApiV1ContributorsGet({
      query: q as ContributorsApiV1ContributorsGetData['query'],
    })
    if (mine !== seq) return // a newer read owns the chart now
    ownFailed.value = !response?.ok || !data
    if (ownFailed.value) logger.warn('handled_lens_failed', { status: response?.status })
    else ownSeries.value = (data as { handled_over_time?: ActivityPoint[] }).handled_over_time ?? []
    ownSettled.value = true
  },
  { immediate: true, deep: true },
)

const shown = computed(() => (fed.value ? props.series! : ownSeries.value))
const isSettled = computed(() => (fed.value ? props.settled : ownSettled.value))
const isFailed = computed(() => (fed.value ? props.failed : ownFailed.value))

const totalHandled = computed(() => shown.value.reduce((n, p) => n + p.count, 0))
const option = computed(() => buildAuditLensOption(shown.value, 'day', 'handled'))
const quiet = computed(() => isSettled.value && !isFailed.value && totalHandled.value === 0)

function onPointClick(params: { dataIndex: number }) {
  const bucket = shown.value[params.dataIndex]?.date
  if (!bucket) return
  const t = bucketEndT(bucket, Date.now(), 'day')
  if (t === null) {
    timeTravel.backToNow()
    return
  }
  timeTravel.rewindTo(t)
  timeTravel.setWindow(timeTravel.windowDays, `→ ${lastDataAt(t)}`)
}
</script>

<template>
  <section class="ingest-lens" :class="{ 'il-quiet': quiet }" aria-label="Handled findings">
    <div class="il-head">
      <h2 class="il-title">Handled findings</h2>
      <span class="il-sub"
        >settling actions per day · {{ timeTravel.windowLabel.toLowerCase() }} · resolved ·
        not affected · risk accepted · acknowledged</span
      >
    </div>
    <!-- pre-data: a shimmer where the chart will be — never the amber claim (issue 355) -->
    <UiSkeleton v-if="!isSettled" :height="84" radius="sm" label="Loading handled findings" class="skel-gap" />
    <p v-else-if="isFailed" class="il-empty">Handled-findings activity unavailable.</p>
    <p v-else-if="totalHandled === 0" class="il-empty">
      No findings were handled in this window.<template v-if="fed"> The board below is empty too.</template>
    </p>
    <div v-else title="Click a bucket to view the whole app as of its end">
      <EChart :option="option" :height="84" @point-click="onPointClick" />
    </div>
  </section>
</template>

<style scoped>
/* the ingest lens's card grammar verbatim — one strip language for every lens */
.ingest-lens {
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
  margin: 0;
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink);
}
.il-sub {
  font-size: var(--text-control);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
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

<script setup lang="ts">
/**
 * The Overview chart "Vulnerabilities over time" as a dashboard panel (issue 1176): new and
 * resolved findings per day, one set of lines per scanner, never merged — `GET /trends/findings`.
 * Only the lines by scanner (decision D4 A): the split by severity is a now-only read, and a
 * panel shows every T. The scanner switch picks lines from the answer, so it starts no read.
 *
 * Self-contained per DESIGN.md section 10 — `(clusterId, t, windowDays, scanner)` in, its own
 * fetch and loading/empty/error states.
 */
import { computed, ref, watch } from 'vue'

import { client } from '@/api/client'
import { findingsTrendApiV1TrendsFindingsGet } from '@/api/generated'
import {
  buildFindingsTrendOption,
  emptyTrendNote,
  trendForScanner,
  type FindingsTrendData,
} from '@/charts/buildFindingsTrendOption'
import { buildTrendQuery, isSubDayWindow } from '@/charts/buildTrendQuery'
import EChart from '@/components/charts/EChart.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import type { ScannerLens } from '@/lib/scannerLens'
import { useTimeTravelStore } from '@/stores/timeTravel'

const props = defineProps<{
  clusterId: string
  /** the rewound T, `null` = now */
  t: string | null
  windowDays: number
  scanner: ScannerLens
}>()

const timeTravel = useTimeTravelStore()

const EMPTY: FindingsTrendData = { new: {}, resolved: {} }
const trend = ref<FindingsTrendData>(EMPTY)
const failed = ref(false)
// no claim before evidence: "no new or resolved findings" only once an answer has come
const settled = ref(false)
/** the cluster the lines on screen belong to: another tenant's lines would be a lie */
let trendFor: string | null = null

let seq = 0
watch(
  () => [props.clusterId, props.t, props.windowDays] as const,
  async ([id, t, days]) => {
    const mine = ++seq
    if (id !== trendFor) {
      settled.value = false
      trend.value = EMPTY
      trendFor = id
    }
    const { data, response } = await findingsTrendApiV1TrendsFindingsGet({
      client,
      query: buildTrendQuery(id, days, t) as never,
    })
    if (mine !== seq) return // a newer read owns the panel now
    failed.value = !response?.ok || !data
    if (failed.value) {
      logger.warn('findings_trend_panel_failed', { status: response?.status })
      trend.value = EMPTY
    } else {
      const d = data as Partial<FindingsTrendData>
      trend.value = { new: d.new ?? {}, resolved: d.resolved ?? {} }
    }
    settled.value = true
  },
  { immediate: true },
)

const option = computed(() => buildFindingsTrendOption(trendForScanner(trend.value, props.scanner)))
const note = computed(() => emptyTrendNote(option.value, 'scanner'))
const subDay = computed(() => isSubDayWindow(props.windowDays))
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <h2>Vulnerabilities over time</h2>
        <p class="card-sub">
          new per day · {{ timeTravel.windowLabel.toLowerCase() }} · resolved = scan-observed
        </p>
      </div>
    </div>
    <div class="card-body">
      <UiSkeleton v-if="!settled" :height="250" radius="sm" label="Loading vulnerabilities over time" />
      <p v-else-if="failed" class="empty-row trend-empty" role="alert">Vulnerability trend unavailable.</p>
      <p v-else-if="note" class="empty-row trend-empty">{{ note }}</p>
      <EChart v-else :option="option" :height="250" />
      <p v-if="subDay" class="chart-note">Trend at daily resolution: chart covers the last 1 day.</p>
    </div>
  </section>
</template>

<style scoped>
/* the paddings of the Overview card, so the panel stands on its own on any host */
.card-head {
  align-items: flex-start;
  padding: 14px 16px 0;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.card-body {
  padding: 10px 16px 14px;
}
/* holds the chart's height, so the card doesn't jump when a range turns up empty */
.trend-empty {
  display: grid;
  place-items: center;
  min-height: 250px;
  margin: 0;
}
.chart-note {
  margin: 6px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
</style>

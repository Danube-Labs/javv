<script setup lang="ts">
/**
 * "Data as of T; scanner silent since T′" (FR-6/D20, audit m-7) — a read-time view over
 * GET /api/v1/scanners/freshness, never written by the staleness sweep. Shown when any
 * (cluster, scanner) has been silent past the freshness window; re-checked on a 10-min poll
 * (staleness develops over days — a pinned tab must learn about it without a reload).
 * Urgency treatment (operator ruling 2026-07-10): down-ramp red, alert icon, role=alert —
 * a silent scanner is a broken pipeline, not a mild advisory.
 */
import { computed, onUnmounted, ref, watch } from 'vue'

import GuideLink from '@/components/about/GuideLink.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { client } from '@/api/client'
import { scannerFreshnessApiV1ScannersFreshnessGet } from '@/api/generated'
import { useClusterStore } from '@/stores/cluster'
import { useStalenessStore } from '@/stores/staleness'
import { logger } from '@/lib/logger'
import {
  checkRows,
  lastDataAt,
  nextFreshnessCheck,
  silentFor,
  silentRows,
  type FreshnessCheck,
  type FreshnessRow,
} from '@/system/freshness'

const POLL_MS = 10 * 60_000

const clusterStore = useClusterStore()
const staleness = useStalenessStore()
const check = ref<FreshnessCheck>({ kind: 'pending' })

async function fetchFreshness() {
  const id = clusterStore.selectedId
  if (!id) return
  // null = no response at all: the request never reached the server
  let status: number | null = null
  try {
    const { data, response } = await scannerFreshnessApiV1ScannersFreshnessGet({
      client,
      query: { cluster_id: id },
    })
    if (clusterStore.selectedId !== id) return
    if (response?.ok && data) {
      const rows = (data as { scanners: FreshnessRow[] }).scanners ?? []
      check.value = nextFreshnessCheck(check.value, { rows, at: Date.now() })
      return
    }
    status = response?.status ?? null
  } catch {
    if (clusterStore.selectedId !== id) return
  }
  logger.warn('scanner_freshness_fetch_failed', { status })
  check.value = nextFreshnessCheck(check.value, null)
}

const timer = setInterval(() => void fetchFreshness(), POLL_MS)
onUnmounted(() => clearInterval(timer))

watch(
  () => clusterStore.selectedId,
  (id) => {
    check.value = { kind: 'pending' }
    void fetchFreshness()
    // the live window (FR-6/D20): the banner thresholds on the cluster's EFFECTIVE timers —
    // what the settings panel edits — never a build-time constant
    if (id) void staleness.loadFor(id)
  },
  { immediate: true },
)

const silent = computed(() => silentRows(checkRows(check.value), staleness.bannerThresholdS))
/** When the kept result was last current; set only while a later read has failed. */
const lastChecked = computed(() =>
  check.value.kind === 'outdated' ? lastDataAt(new Date(check.value.checkedAt).toISOString()) : null,
)
const clusterName = computed(() => clusterStore.selected?.cluster_name ?? clusterStore.selectedId)
</script>

<template>
  <Transition name="t-fade">
    <div v-if="silent.length" class="sys-line tone-down" role="alert">
      <AppIcon class="sys-icon" name="alert" :size="15" />
      <span>
        The data of <strong class="mono">{{ clusterName }}</strong> can be old:
        <template v-for="(row, i) in silent" :key="row.scanner">
          <template v-if="i > 0"> · </template>
          <strong>{{ row.scanner }}</strong> sent no data for {{ silentFor(row.silent_for_seconds) }}
          (last data <span class="mono">{{ lastDataAt(row.last_ingest_at) }}</span>)</template
        >.
        <template v-if="lastChecked"> JAVV last checked at {{ lastChecked }}. The latest check failed.</template>
        <GuideLink section="scans-and-freshness" label="What this means" />
      </span>
    </div>
    <!-- freshness unknown is a degraded state, not a note: the health ramp's amber step between
         fine (no line) and down (the red banner), operator ruling on built specimens 2026-10-01 -->
    <div v-else-if="check.kind === 'failed' || lastChecked" class="sys-line tone-degraded" role="status">
      <AppIcon class="sys-icon" name="alert" :size="15" />
      <span v-if="check.kind === 'failed'"
        >The last check of the scanner freshness of <strong class="mono">{{ clusterName }}</strong> failed.
        JAVV tries again every 10 minutes.</span
      >
      <span v-else
        >JAVV last checked the scanner freshness at {{ lastChecked }}. The latest check failed. JAVV tries
        again every 10 minutes.</span
      >
    </div>
  </Transition>
</template>

<script setup lang="ts">
/**
 * Image detail — per-digest drill-down (M9c slice 3; SCREENS §8). Identity is the content
 * digest; `repo:tag` ride along as query context. The scanner lens is a READ lens: it swaps
 * which scanner's committed findings + facets are shown — never merges (per-scanner sacred).
 * Severity cards and rows come from the same server reads the Findings screen uses
 * (`image_digest` scoped), so the two screens can never disagree; `as_of` rides every query
 * (T<now = the M8b reader, as-scanned).
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import type {
  FacetFindingsApiV1FindingsFacetsGetData,
  ImageTimelineApiV1ImagesTimelineGetData,
  ListRunningImagesApiV1ImagesGetData,
} from '@/api/generated'
import {
  facetFindingsApiV1FindingsFacetsGet,
  imageTimelineApiV1ImagesTimelineGet,
  listRunningImagesApiV1ImagesGet,
} from '@/api/generated'
import IngestLens from '@/components/dashboards/IngestLens.vue'
import DigestSubTimeline from '@/components/images/DigestSubTimeline.vue'
import ImageFindingsPanel from '@/components/images/ImageFindingsPanel.vue'
import { buildImageAtTQuery } from '@/images/buildImageAtTQuery'
import { notYetScannedAt, type TimelineEvent } from '@/images/subTimeline'
import type { ImageRow } from '@/stores/images'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { useApi } from '@/composables/useApi'
import { readFailureCopy } from '@/findings/failureCopy'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { lastDataAt } from '@/system/freshness'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { CHART_SEV, type Severity } from '@/styles/tokens'

const CARD_SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low']
const SCANNER_OPTS = [
  { value: 'trivy', label: 'trivy' },
  { value: 'grype', label: 'grype' },
] as const

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const { withGlobals } = useApi()

const digest = computed(() => String(route.params.digest ?? ''))
const repo = computed(() => (route.query.repo ? String(route.query.repo) : null))
const tag = computed(() => (route.query.tag ? String(route.query.tag) : null))
const title = computed(() =>
  repo.value ? `${repo.value.split('/').at(-1)}${tag.value ? `:${tag.value}` : ''}` : 'Image',
)

const scanner = ref<'trivy' | 'grype'>('trivy')

/* ---- severity cards: the lens scanner's facet buckets, image-scoped ---- */
const facets = ref<Record<string, { key: string; count: number }[]>>({})
const facetsFailed = ref(false)

const baseQuery = computed(() =>
  clusterStore.selectedId
    ? withGlobals({
        cluster_id: clusterStore.selectedId,
        image_digest: digest.value,
        scanner: scanner.value,
      })
    : null,
)

async function loadFacets() {
  if (!baseQuery.value) return
  const { data, response } = await facetFindingsApiV1FindingsFacetsGet({
    query: baseQuery.value as FacetFindingsApiV1FindingsFacetsGetData['query'],
  })
  if (response?.ok && data) {
    facets.value = (data as { facets: typeof facets.value }).facets ?? {}
    facetsFailed.value = false
  } else {
    facetsFailed.value = true
    logger.warn('image_detail_facets_failed', { status: response?.status })
  }
}

watch(baseQuery, () => void loadFacets(), { immediate: true })

const sevCount = (s: Severity) => facets.value.severity?.find((b) => b.key === s)?.count ?? 0
const presentTotal = computed(() => facets.value.present?.find((b) => b.key === 'true')?.count ?? 0)

/* ---- the two questions (D38/H6): runtime inventory vs as-scanned — never conflated ---- */
const inventoryRow = ref<ImageRow | null>(null)
const inventoryKnown = ref<boolean | null>(null) // null = loading; false = no committed inventory at T
const inventoryAt = ref<string | null>(null) // WHEN that truth was committed — the provenance stamp
async function loadInventoryAtT() {
  if (!clusterStore.selectedId) return
  const q = buildImageAtTQuery(clusterStore.selectedId, digest.value, scanner.value, timeTravel.t)
  const { data, response } = await listRunningImagesApiV1ImagesGet({
    query: q.runtime_inventory_at_T as ListRunningImagesApiV1ImagesGetData['query'],
  })
  if (response?.ok && data) {
    const body = data as { inventory: { completed_at: string | null } | null; images: ImageRow[] }
    inventoryKnown.value = body.inventory !== null
    inventoryAt.value = body.inventory?.completed_at ?? null
    inventoryRow.value = body.images.find((i) => i.image_digest === digest.value) ?? null
  } else {
    inventoryKnown.value = null
    logger.warn('image_detail_inventory_failed', { status: response?.status })
  }
}
watch([() => clusterStore.selectedId, () => timeTravel.t, digest], () => void loadInventoryAtT(), {
  immediate: true,
})

/* ---- build history: the committed scan-event trail of this repo:tag ---- */
const timeline = ref<TimelineEvent[]>([])
const timelineFailed = ref(false)
const timelineFailedStatus = ref<number | null>(null)
async function loadTimeline() {
  if (!clusterStore.selectedId || !repo.value || !tag.value) return
  const { data, response } = await imageTimelineApiV1ImagesTimelineGet({
    query: {
      cluster_id: clusterStore.selectedId,
      image_repo: repo.value,
      tag: tag.value,
    } as ImageTimelineApiV1ImagesTimelineGetData['query'],
  })
  timelineFailed.value = !response?.ok || !data
  timelineFailedStatus.value = response?.status ?? null
  if (!timelineFailed.value) {
    timeline.value = (data as { events: TimelineEvent[] }).events ?? []
  } else {
    timeline.value = []
    logger.warn('image_detail_timeline_failed', { status: response?.status })
  }
}
watch([() => clusterStore.selectedId, repo, tag], () => void loadTimeline(), { immediate: true })

// an unread timeline is not an empty one: never "not yet scanned" on a refused read (issue 833, F5)
const notYetScanned = computed(
  () => !timelineFailed.value && notYetScannedAt(timeline.value, scanner.value, timeTravel.t),
)

/** The current lens scanner's most recent committed scan ≤ T — the findings answer's stamp. */
const lastScanAt = computed(() => {
  const cut = timeTravel.t
  return timeline.value
    .filter((e) => e.scanner === scanner.value && (cut === null || e['@timestamp'] <= cut))
    .reduce<string | null>(
      (max, e) => (max === null || e['@timestamp'] > max ? e['@timestamp'] : max),
      null,
    )
})

const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <div class="screen">
    <UiButton variant="quiet" class="back-btn" @click="router.push('/images')">
      <AppIcon name="arrowback" :size="13" /> Running images
    </UiButton>
    <div class="screen-head">
      <div class="img-id-head">
        <div class="img-cube" aria-hidden="true"><AppIcon name="cube" :size="22" /></div>
        <div>
          <h1>{{ title }}</h1>
          <p v-if="repo" class="screen-sub mono-cell">{{ repo }}{{ tag ? `:${tag}` : '' }}</p>
          <p class="digest-line mono-cell" :title="digest">
            <AppIcon name="key" :size="11" />{{ digest }}
          </p>
          <div v-if="inventoryRow" class="img-meta">
            <span class="mono-cell"><b>{{ fmt(inventoryRow.replicas ?? 0) }}</b> replica{{ (inventoryRow.replicas ?? 0) === 1 ? '' : 's' }} at last sweep</span>
            <span class="mono-cell">{{ inventoryRow.namespaces.join(', ') }}</span>
          </div>
        </div>
      </div>
      <div class="head-actions">
        <span class="lens-label">Showing results from</span>
        <UiSegControl v-model="scanner" :options="SCANNER_OPTS" label="Showing results from" head />
      </div>
    </div>

    <!-- two distinct questions, two answers — never conflated (D38/H6) -->
    <div class="stat-band two-q">
      <div class="stat-cell">
        <span class="stat-label"><i class="stat-dot" style="background: var(--teal)" />running {{ timeTravel.isNow ? 'now' : 'at T' }}?</span>
        <span class="stat-num tq-ans">
          <span v-if="inventoryKnown === null" class="muted-dash">-</span>
          <template v-else-if="inventoryKnown === false">unknown</template>
          <template v-else-if="inventoryRow"
            >yes · {{ fmt(inventoryRow.replicas ?? 0) }} replica{{
              (inventoryRow.replicas ?? 0) === 1 ? '' : 's'
            }}</template
          >
          <template v-else>no</template>
        </span>
        <span class="stat-sub"
          >runtime inventory<template v-if="inventoryKnown === false">
            · none committed at this T</template
          ><template v-else-if="inventoryAt"> · committed {{ lastDataAt(inventoryAt) }}</template></span
        >
      </div>
      <div class="stat-cell">
        <span class="stat-label"><i class="stat-dot" style="background: var(--slate)" />what did {{ scanner }} find?</span>
        <span class="stat-num tq-ans">
          <template v-if="notYetScanned">not yet scanned</template>
          <template v-else>{{ fmt(presentTotal) }} findings</template>
        </span>
        <span class="stat-sub"
          >as-scanned, not as-running<template v-if="lastScanAt">
            · last scan {{ lastDataAt(lastScanAt) }}</template
          ></span
        >
      </div>
    </div>

    <!-- per-digest build history: a rebuilt tag is a NEW digest — never a silent gap -->
    <section class="card tl-card">
      <div class="card-head">
        <div>
          <h2>Build history</h2>
          <p class="card-sub">{{ scanner }}'s committed scans of this tag · a rebuilt tag is a new digest</p>
        </div>
      </div>
      <div class="card-body">
        <p v-if="timelineFailed" class="load-error" role="alert">
          {{ readFailureCopy(timelineFailedStatus, 'Build history unavailable. Check the backend connection.') }}
        </p>
        <DigestSubTimeline
          v-else
          :events="timeline"
          :scanner="scanner"
          :t="timeTravel.t"
          :current-digest="digest"
        />
      </div>
    </section>

    <div v-if="notYetScanned" class="card first-run">
      <h2>Not yet scanned then</h2>
      <p>
        No committed {{ scanner }} scan of this tag exists at or before this T. Reach is bounded
        by this cluster's retained data.
      </p>
    </div>

    <template v-else>
      <IngestLens
        v-if="clusterStore.selectedId"
        class="detail-lens"
        :cluster-id="clusterStore.selectedId"
      />
      <!-- per-scanner severity cards: one scanner's buckets only — the lens swaps, never merges -->
      <div class="stat-band sev-band">
        <div v-for="s in CARD_SEVERITIES" :key="s" class="stat-cell">
          <span class="stat-label"><i class="stat-dot" :style="{ background: CHART_SEV[s] }" />{{ s }}</span>
          <span class="stat-num">{{ fmt(sevCount(s)) }}</span>
        </div>
        <div class="stat-cell">
          <span class="stat-label"><i class="stat-dot" style="background: var(--slate)" />findings · {{ scanner }}</span>
          <span class="stat-num">{{ fmt(presentTotal) }}</span>
        </div>
      </div>

      <ImageFindingsPanel :digest="digest" :scanner="scanner" />
    </template>
  </div>
</template>

<style scoped>
/* the identity panel (prototype .img-detail-head — a card, not bare text on the canvas) */
.screen-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  /* the scanner switch drops under the identity block when the two don't fit side by side */
  flex-wrap: wrap;
  gap: 12px 16px;
  margin-bottom: 16px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 16px 20px;
}
.back-btn {
  margin-bottom: 10px;
}
.screen-head h1 {
  margin: 0 0 4px;
}
.screen-sub {
  margin: 0;
  color: var(--ink);
  font-size: var(--text-body);
}
.img-id-head {
  display: flex;
  gap: 14px;
  align-items: flex-start;
  min-width: 0;
}
.img-id-head > div {
  min-width: 0;
}
.img-cube {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--slate);
  color: var(--side-brand-fg);
  display: grid;
  place-items: center;
  flex: none;
  margin-top: 2px;
}
.digest-line {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 4px 0 0;
  font-size: var(--text-sm);
  color: var(--ink);
  max-width: 720px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.img-meta {
  display: flex;
  gap: 14px;
  margin-top: 6px;
  font-size: var(--text-sm);
  color: var(--ink);
}
.two-q {
  grid-template-columns: repeat(2, 1fr);
  margin-bottom: 16px;
}
.stat-dot-inv {
  background: var(--teal);
}
.stat-dot-scan {
  background: var(--slate);
}
.tq-ans {
  font-size: var(--text-card-title);
}
.tl-card {
  margin: 0 0 16px;
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  /* cube (44px) + its gap (14px): a dropped switch lines up under the title, not the cube */
  margin-left: 58px;
}
.lens-label {
  font-size: var(--text-sm);
  color: var(--soft);
}

/* joined stat band — read-only cards (the ruled Nuxt grammar) */
/* the joined stat-band SKIN lives in base.css (issue 368) — only this screen's layout here */
.sev-band {
  grid-template-columns: repeat(5, 1fr);
  margin-bottom: 16px;
}
.detail-lens {
  margin-bottom: 16px;
}

.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  margin-top: 16px;
}
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 0;
}
.card-head h2 {
  margin: 0;
  font-size: var(--text-card-title);
  font-weight: 600;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.card-body {
  padding: 10px 16px 14px;
}
.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
.first-run {
  padding: 48px 16px;
  text-align: center;
  color: var(--soft);
}
.first-run h2 {
  color: var(--ink);
  margin: 0 0 6px;
}
</style>

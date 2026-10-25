<script setup lang="ts">
/**
 * Overview "Riskiest images" card (§8.5 ruling 2026-07-16: kept alongside TopComponentsCard):
 * every running image with findings, ranked by the server's per-image severity buckets under
 * the scanner lens — critical first, then down the ramp — paged as display slices through the
 * shared GridPager. Every number is the images read's server-decorated `severity_by_scanner`;
 * the lens picks a scanner's buckets, `all` adds the per-scanner counts (additive, same
 * grammar as the fleet strip — never a cross-scanner dedupe). Rows open the image detail.
 * It reads the images itself, apart from the Running images screen's store, so it renders
 * alone on a dashboard with its own loading and error states.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { client } from '@/api/client'
import { listRunningImagesApiV1ImagesGet } from '@/api/generated'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import RowLink from '@/components/ui/RowLink.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import { fmt, type ScannerLens } from '@/lib/scannerLens'
import { useClusterStore } from '@/stores/cluster'
import type { ImageRow } from '@/stores/images'
import { useTimeTravelStore } from '@/stores/timeTravel'

const RANK_KEYS = ['crit', 'high', 'med', 'low'] as const

const props = withDefaults(
  defineProps<{
    scanner: ScannerLens
    /** rows a page; a dashboard panel sets it from its height */
    pageSize?: number
  }>(),
  { pageSize: 10 },
)

const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()

const images = ref<ImageRow[]>([])
/** no committed inventory yet: JAVV does not know what runs, which is not an empty cluster */
const unknown = ref(false)
/** the time that answer is for: the text names that time, not one whose read is still open */
const unknownAt = ref<string | null>(null)
const failed = ref(false)
// no claim before evidence: "No image findings" only once an answer has come
const settled = ref(false)

/** the cluster the images on screen belong to: another tenant's images would be a lie */
let imagesFor: string | null = null

let seq = 0
watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  async ([id, t]) => {
    const mine = ++seq // also when no read starts: an older read in flight must not land
    if (id !== imagesFor) {
      settled.value = false
      images.value = []
      imagesFor = id
    }
    if (!id) return
    const { data, response } = await listRunningImagesApiV1ImagesGet({
      client,
      query: { cluster_id: id, ...(t ? { as_of: t } : {}) } as never,
    })
    if (mine !== seq) return // a newer read owns the card now
    failed.value = !response?.ok || !data
    if (failed.value) logger.warn('riskiest_images_failed', { status: response?.status })
    else {
      const body = data as { inventory?: unknown; images?: ImageRow[] }
      unknown.value = body.inventory === null
      unknownAt.value = t
      images.value = body.images ?? []
    }
    settled.value = true
  },
  { immediate: true },
)

/** A row's severity bucket under the lens: one scanner's committed counts, or their sum. */
function sev(row: ImageRow, key: (typeof RANK_KEYS)[number]): number {
  const per = row.severity_by_scanner ?? {}
  if (props.scanner !== 'all') return per[props.scanner]?.[key] ?? 0
  return Object.values(per).reduce((n, b) => n + (b[key] ?? 0), 0)
}

const ordered = computed(() =>
  images.value
    .map((r) => ({ row: r, rank: RANK_KEYS.map((k) => sev(r, k)) }))
    .filter((x) => x.rank.some((n) => n > 0))
    .sort((a, b) => {
      for (let i = 0; i < a.rank.length; i++) {
        if (a.rank[i] !== b.rank[i]) return (b.rank[i] ?? 0) - (a.rank[i] ?? 0)
      }
      return 0
    }),
)

const page = ref(0)
const size = ref(props.pageSize)
watch([ordered], () => {
  page.value = 0
})
watch(
  () => props.pageSize,
  (next) => setSize(next),
)
const shown = computed(() =>
  ordered.value.slice(page.value * size.value, (page.value + 1) * size.value),
)
const hasNext = computed(() => (page.value + 1) * size.value < ordered.value.length)
function setSize(next: number) {
  size.value = next
  page.value = 0
}

const imageRoute = (row: ImageRow) => ({
  path: `/images/${encodeURIComponent(row.image_digest)}`,
  query: { repo: row.image_repo, tag: row.tag },
})
function open(row: ImageRow) {
  void router.push(imageRoute(row))
}
</script>

<template>
  <section class="tbl-card">
    <div class="card-head">
      <div>
        <h2>Riskiest images</h2>
        <p class="card-sub">ranked by critical, then high</p>
      </div>
      <UiButton variant="mini" @click="router.push('/images')">View inventory</UiButton>
    </div>
    <UiSkeleton
      v-if="!settled"
      class="skel-pad"
      :height="220"
      radius="sm"
      label="Loading riskiest images"
    />
    <p v-else-if="failed" class="empty-row" role="alert">Riskiest images unavailable.</p>
    <p v-else-if="ordered.length === 0 && unknown" class="empty-row">
      {{
        unknownAt === null
          ? 'No inventory committed yet. Images show once a scanner cycle completes.'
          : 'No inventory committed at this point in time.'
      }}
    </p>
    <p v-else-if="ordered.length === 0" class="empty-row">
      No image findings in the running inventory.
    </p>
    <template v-else>
      <div class="tbl-wrap">
        <table class="tbl tbl-dense tbl-hover">
          <thead>
            <tr>
              <th>Image</th>
              <th class="r fit">Critical</th>
              <th class="r fit">High</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="x in shown"
              :key="x.row.image_digest"
              :title="`Open ${x.row.image_repo}:${x.row.tag}`"
              @click="open(x.row)"
            >
              <td class="mono-cell img-link">
                <RowLink :to="imageRoute(x.row)" @open="open(x.row)">
                  {{ x.row.image_repo }}:{{ x.row.tag
                  }}<AppIcon class="cell-go" name="chevron" :size="11" />
                </RowLink>
              </td>
              <td class="r fit mono-cell sm strong">
                <span :class="{ 'crit-alarm': (x.rank[0] ?? 0) > 0 }">{{ fmt(x.rank[0] ?? 0) }}</span>
              </td>
              <td class="r fit mono-cell sm">{{ fmt(x.rank[1] ?? 0) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <GridPager
        :total="ordered.length"
        :page="page"
        :size="size"
        :shown="shown.length"
        :has-prev="page > 0"
        :has-next="hasNext"
        @prev="page -= 1"
        @next="page += 1"
        @update:size="setSize"
      />
    </template>
  </section>
</template>

<style scoped>
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 10px;
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
.strong {
  font-weight: 700;
  color: var(--ink);
}
.skel-pad {
  margin: 0 16px 14px;
}
.crit-alarm {
  color: var(--sev-critical-fg);
}
/* the affordance carrier — same convention as the grid's cve-link */
.img-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .img-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .img-link {
    transition: none;
  }
}
</style>

<script setup lang="ts">
/**
 * Overview "Top components" card (the prototype card cut at M9c, restored — §8.5 ruling
 * 2026-07-16: kept alongside RiskiestImagesCard): the server's ≤100-package board with a
 * PER-SCANNER unique-CVE count each, paged as display slices through the shared GridPager
 * (the contributors-leaderboard model). The lens picks a scanner's uniques; `all` adds them
 * (additive, like every facet) — a cross-scanner distinct count would be a merge. A now-only
 * read (the route 422s at a past T — the card says so instead of guessing). Rows click through
 * to the findings grid contains-filtered on the package.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { client } from '@/api/client'
import { topComponentsFindingsApiV1FindingsTopComponentsGet } from '@/api/generated'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import RowLink from '@/components/ui/RowLink.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { fmt, type ScannerLens } from '@/lib/scannerLens'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'

interface ComponentRow {
  package_name: string
  count: number
  unique_cves_by_scanner: Record<string, number>
}

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

const rows = ref<ComponentRow[]>([])
const failed = ref(false)
// no claim before evidence: "No component data yet" only once an answer has landed
const settled = ref(false)

watch(
  () => [clusterStore.selectedId, timeTravel.t] as const,
  async ([id, t], old) => {
    if (!id || t !== null) return // now-only read — the template shows the rewound note
    if (old && old[0] !== id) {
      settled.value = false // another tenant's board would be a lie
      rows.value = []
    }
    const { data, response } = await topComponentsFindingsApiV1FindingsTopComponentsGet({
      client,
      query: { cluster_id: id } as never,
    })
    failed.value = !response?.ok || !data
    if (!failed.value) {
      rows.value = (data as { components: ComponentRow[] }).components ?? []
    } else {
      logger.warn('top_components_load_failed', { status: response?.status })
    }
    settled.value = true
  },
  { immediate: true },
)

/** The lens count: one scanner's unique CVEs, or the per-scanner sum (never a cross-scanner
 * distinct count — the server doesn't compute one). */
function uniques(row: ComponentRow, scanner: ScannerLens): number {
  if (scanner !== 'all') return row.unique_cves_by_scanner[scanner] ?? 0
  return Object.values(row.unique_cves_by_scanner).reduce((n, v) => n + v, 0)
}

/** The server picks the board by finding rows; the display ranks it by the lens's uniques
 * so the column reads as the ranking the subtitle claims. */
const ordered = computed(() =>
  [...rows.value]
    .map((r) => ({ row: r, uniq: uniques(r, props.scanner) }))
    .filter((x) => x.uniq > 0)
    .sort((a, b) => b.uniq - a.uniq),
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

const findingsRoute = (pkg: string) => ({ path: '/findings', query: { q: pkg } })
function goFindings(pkg: string) {
  void router.push(findingsRoute(pkg))
}
</script>

<template>
  <section class="tbl-card">
    <div class="card-head">
      <div>
        <h2>Top components</h2>
        <p class="card-sub">by unique vulnerabilities</p>
      </div>
    </div>
    <p v-if="!timeTravel.isNow" class="empty-row">
      Component ranking is a current-state read, unavailable at a rewound T.
    </p>
    <UiSkeleton
      v-else-if="!settled"
      class="skel-pad"
      :height="220"
      radius="sm"
      label="Loading top components"
    />
    <p v-else-if="failed" class="empty-row" role="alert">Component ranking unavailable.</p>
    <p v-else-if="ordered.length === 0" class="empty-row">No component data yet.</p>
    <template v-else>
      <div class="tbl-wrap">
        <table class="tbl tbl-dense tbl-hover">
          <thead>
            <tr>
              <th>Component</th>
              <th class="r fit">Unique CVEs</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="x in shown"
              :key="x.row.package_name"
              :title="`Open findings mentioning ${x.row.package_name}`"
              @click="goFindings(x.row.package_name)"
            >
              <td class="mono-cell pkg-link">
                <RowLink :to="findingsRoute(x.row.package_name)" @open="goFindings(x.row.package_name)">
                  {{ x.row.package_name }}<AppIcon class="cell-go" name="chevron" :size="11" />
                </RowLink>
              </td>
              <td class="r fit mono-cell sm strong">{{ fmt(x.uniq) }}</td>
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
/* the affordance carrier — same convention as the grid's cve-link */
.pkg-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .pkg-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .pkg-link {
    transition: none;
  }
}
</style>

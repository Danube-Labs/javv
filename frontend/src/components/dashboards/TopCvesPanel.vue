<script setup lang="ts">
/**
 * Top CVEs (issue 1176): the CVEs with the most findings, ranked by the store
 * (`GET /findings/top-values?by=cve_id`, at most 100) and paged by the shared GridPager. On one
 * scanner the read asks the store to rank by that scanner; on all scanners the count adds the
 * two, as every card's "all" does. The severity tag is the highest severity among the findings
 * in the count. A now-only read: at a past T the panel says so and names the way back to now.
 *
 * Self-contained per DESIGN.md section 10 — `(clusterId, t, scanner, filters)` in, its own read
 * and loading/empty/error states.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { client } from '@/api/client'
import { topValuesFindingsApiV1FindingsTopValuesGet, type ViewPreset } from '@/api/generated'
import SevChip from '@/components/chips/SevChip.vue'
import GridPager from '@/components/findings/GridPager.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import RowLink from '@/components/ui/RowLink.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { panelFindingsQuery, panelQuery } from '@/dashboards/panelFilters'
import { logger } from '@/lib/logger'
import { fmt, type ScannerLens } from '@/lib/scannerLens'
import { SEVERITIES } from '@/styles/tokens'

export interface CveRow {
  value: string
  count: number
  count_by_scanner: Record<string, number>
  severity_by_scanner: Record<string, Record<string, number>>
}

const props = withDefaults(
  defineProps<{
    clusterId: string
    /** the rewound T, `null` = now */
    t: string | null
    scanner: ScannerLens
    pageSize?: number
    /** a dashboard panel's own filters (issue 999) */
    filters?: ViewPreset | null
  }>(),
  { pageSize: 10, filters: null },
)

const router = useRouter()

const rows = ref<CveRow[]>([])
const failed = ref(false)
// no claim before evidence: "No CVE in the findings" only once an answer has come
const settled = ref(false)
/** the cluster the rows on screen belong to: another tenant's board would be a lie */
let rowsFor: string | null = null

let seq = 0
watch(
  // the filters by value: an equal filters object starts no new read
  () => [props.clusterId, props.t, props.scanner, JSON.stringify(props.filters ?? null)] as const,
  async ([id, t, scanner]) => {
    const mine = ++seq // also when no read starts: an older read in flight must not land
    if (id !== rowsFor) {
      settled.value = false
      rows.value = []
      rowsFor = id
    }
    if (t !== null) return // now-only read — the template shows the rewound note
    const { data, response } = await topValuesFindingsApiV1FindingsTopValuesGet({
      client,
      query: {
        ...panelQuery({ cluster_id: id }, props.filters),
        by: 'cve_id',
        ...(scanner === 'all' ? {} : { scanner }),
      } as never,
    })
    if (mine !== seq) return // a newer read owns the board now
    failed.value = !response?.ok || !data
    if (failed.value) logger.warn('top_cves_panel_failed', { status: response?.status })
    rows.value = failed.value ? [] : ((data as { values?: CveRow[] }).values ?? [])
    settled.value = true
  },
  { immediate: true },
)

/** The highest severity among the findings of the scanners in the read. */
function highest(row: CveRow): string {
  const present = new Set(
    Object.values(row.severity_by_scanner).flatMap((bySev) =>
      Object.entries(bySev)
        .filter(([, n]) => n > 0)
        .map(([sev]) => sev),
    ),
  )
  return SEVERITIES.find((s) => present.has(s)) ?? 'unknown'
}

const page = ref(0)
const size = ref(props.pageSize)
watch(rows, () => {
  page.value = 0
})
watch(
  () => props.pageSize,
  (next) => setSize(next),
)
const shown = computed(() => rows.value.slice(page.value * size.value, (page.value + 1) * size.value))
const hasNext = computed(() => (page.value + 1) * size.value < rows.value.length)
function setSize(next: number) {
  size.value = next
  page.value = 0
}

const findingsRoute = (cve: string) => ({ path: '/findings', query: panelFindingsQuery(props.filters, { cve }) })
function goFindings(cve: string) {
  void router.push(findingsRoute(cve))
}
</script>

<template>
  <section class="tbl-card">
    <div class="card-head">
      <div>
        <h2>Top CVEs</h2>
        <p class="card-sub">by findings</p>
      </div>
    </div>
    <p v-if="t !== null" class="empty-row">
      This panel shows only the time now, not the past time that you selected. To see the CVEs, select Back to now.
    </p>
    <UiSkeleton v-else-if="!settled" class="skel-pad" :height="220" radius="sm" label="Loading top CVEs" />
    <p v-else-if="failed" class="empty-row" role="alert">CVE ranking unavailable.</p>
    <p v-else-if="rows.length === 0" class="empty-row">No CVE in the findings.</p>
    <template v-else>
      <div class="tbl-wrap">
        <table class="tbl tbl-dense tbl-hover">
          <thead>
            <tr>
              <th>CVE</th>
              <th class="fit">Severity</th>
              <th class="r fit">Findings</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in shown"
              :key="r.value"
              :title="`Open the findings of ${r.value}`"
              @click="goFindings(r.value)"
            >
              <td class="mono-cell">
                <RowLink :to="findingsRoute(r.value)" @open="goFindings(r.value)">
                  {{ r.value }}<AppIcon class="cell-go" name="chevron" :size="11" />
                </RowLink>
              </td>
              <td class="fit"><SevChip :level="highest(r)" /></td>
              <td class="r fit mono-cell sm strong">{{ fmt(r.count) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <GridPager
        :total="rows.length"
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
  align-items: flex-start;
  padding: 14px 16px 10px;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
</style>

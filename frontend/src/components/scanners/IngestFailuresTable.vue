<script setup lang="ts">
/**
 * Failed ingests for ONE scanner: the pushes the backend refused after checking their token,
 * newest first, server-paged (`GET /scanners/ingest-failures`). Self-contained per DESIGN.md
 * section 10 — `(clusterId, t, windowDays, scanner)` in, its own fetch and its own
 * loading/empty/error states — so it renders on any host, a composed dashboard included.
 *
 * One scanner per panel: the read requires `scanner`, so no row, page or total ever mixes
 * scanners. Read-only by ruling: retries and dead-lettering stay with the scanner, so there is
 * no status column and no Retry action (SCREENS section 12).
 */
import { ref, watch } from 'vue'

import { client } from '@/api/client'
import { scannerIngestFailuresApiV1ScannersIngestFailuresGet } from '@/api/generated'
import GridPager from '@/components/findings/GridPager.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useCursorPager } from '@/composables/useCursorPager'
import { logger } from '@/lib/logger'
import { lastDataAt } from '@/system/freshness'
import {
  buildIngestFailuresQuery,
  type IngestFailureRow,
  type IngestFailuresPage,
  type ScannerName,
} from '@/system/ingestFailures'

const props = defineProps<{
  clusterId: string
  scanner: ScannerName
  /** the rewound T, `null` = now */
  t: string | null
  windowDays: number
}>()

const pager = useCursorPager(10)
const rows = ref<IngestFailureRow[]>([])
const total = ref(0)
const failed = ref(false)
// no claim before evidence: "no failed ingests" only once an answer has landed
const settled = ref(false)

async function load() {
  const { data, response } = await scannerIngestFailuresApiV1ScannersIngestFailuresGet({
    client,
    query: buildIngestFailuresQuery({
      clusterId: props.clusterId,
      scanner: props.scanner,
      windowDays: props.windowDays,
      t: props.t,
      size: pager.size.value,
      cursor: pager.cursor.value,
    }),
  })
  failed.value = !response?.ok || !data
  if (failed.value) {
    logger.warn('ingest_failures_load_failed', { status: response?.status, scanner: props.scanner })
  } else {
    const page = data as unknown as IngestFailuresPage
    rows.value = page.data
    total.value = page.total.value
    pager.landed(page.next_cursor)
  }
  settled.value = true
}

watch(
  () => [props.clusterId, props.scanner, props.t, props.windowDays, pager.size.value] as const,
  ([id], old) => {
    if (old && old[0] !== id) settled.value = false // another tenant's rows would be a lie
    pager.reset()
    void load()
  },
  { immediate: true },
)

function goNext() {
  if (pager.next()) void load()
}
function goPrev() {
  if (pager.prev()) void load()
}
</script>

<template>
  <section class="tbl-card" :aria-label="`Failed ingests of ${scanner}`">
    <div class="tbl-card-head">
      <div>
        <h3>Failed ingests</h3>
        <p class="tbl-card-sub">The scans that the backend refused in this range. Only the scanner can send a scan again.</p>
      </div>
    </div>
    <div v-if="!settled" class="skel-rows" aria-busy="true" aria-label="Loading the refused scans">
      <UiSkeleton :height="120" />
    </div>
    <p v-else-if="failed" class="empty-row" role="alert">JAVV cannot show the refused scans. Check the backend connection.</p>
    <p v-else-if="total === 0" class="empty-row">No refused scans in this range.</p>
    <template v-else>
      <div class="tbl-wrap">
        <table class="tbl tbl-dense tbl-hover">
          <thead>
            <tr>
              <th class="fit">When</th>
              <th>Image</th>
              <th class="fit">Stage</th>
              <th>Error</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.failure_id">
              <td class="fit">
                <span class="mono-cell sm nowrap" :title="row['@timestamp']">{{
                  lastDataAt(row['@timestamp'])
                }}</span>
              </td>
              <td>
                <span v-if="row.image_ref" class="mono-cell sm clip" :title="row.image_ref">{{
                  row.image_ref
                }}</span>
                <span v-else class="muted-dash" title="The scan has no image that JAVV can read.">-</span>
              </td>
              <td class="fit">
                <span class="mono-cell sm">{{ row.stage }}</span>
              </td>
              <td>
                <span class="clip" :title="`${row.status} · ${row.error}`"
                  ><span class="mono-cell sm status">{{ row.status }}</span> · {{ row.error }}</span
                >
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <GridPager
        :total="total"
        :page="pager.page.value"
        :size="pager.size.value"
        :shown="rows.length"
        :has-prev="pager.hasPrev.value"
        :has-next="pager.hasNext.value"
        @prev="goPrev"
        @next="goNext"
        @update:size="pager.setSize"
      />
    </template>
  </section>
</template>

<style scoped>
/* a host that stretches the card (a row-aligned grid) keeps the pager at the card's foot */
.tbl-card {
  display: flex;
  flex-direction: column;
}
.tbl-card > .tbl-wrap {
  flex: 1;
}
.skel-rows {
  padding: 0 16px 14px;
}
/* long refs and messages ellipsize in their column; the full text is on hover */
.clip {
  display: block;
  max-width: 0;
  min-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status {
  color: var(--ink);
  font-weight: 700;
}
</style>

<script setup lang="ts">
/**
 * The committed-run timeline under a scanner panel (M9d slice 2) — shared table template +
 * the shared GridPager. The provenance read returns the last N runs (endpoint cap 50, newest
 * first by scan_order); pages here are display slices of that server answer — no client
 * arithmetic beyond slicing. At the cap the header says so: older runs exist but are not
 * fetched (the full history is the ingest lens's job).
 */
import { computed, ref, watch } from 'vue'

import MixBar from '@/components/dashboards/MixBar.vue'
import GridPager from '@/components/findings/GridPager.vue'
import { fmt } from '@/lib/format'
import { lastDataAt } from '@/system/freshness'
import type { Severity } from '@/styles/tokens'

import type { ScanRunRow } from './ScannerStatusCard.vue'

const props = defineProps<{
  runs: ScanRunRow[]
  /** whose committed runs these are — MixBar names it in the tooltip (per-scanner sacred) */
  scanner: string
  /** the fetch asked for this many — runs.length === cap means "there may be older ones" */
  cap: number
}>()

const mix = (run: ScanRunRow): Partial<Record<Severity, number>> =>
  (run.severity ?? {}) as Partial<Record<Severity, number>>

const page = ref(0)
const size = ref(10)
watch(
  () => props.runs,
  () => {
    page.value = 0
  },
)

const shown = computed(() => props.runs.slice(page.value * size.value, (page.value + 1) * size.value))
const hasNext = computed(() => (page.value + 1) * size.value < props.runs.length)
const atCap = computed(() => props.runs.length >= props.cap)

function setSize(next: number) {
  size.value = next
  page.value = 0
}

</script>

<template>
  <div class="tbl-wrap">
    <table class="tbl tbl-dense tbl-hover">
      <thead>
        <tr>
          <th class="fit">Committed{{ atCap ? ` · last ${cap}` : '' }}</th>
          <th>Run</th>
          <th class="mix-col">Mix</th>
          <th class="fit">Images</th>
          <th class="fit">Findings</th>
          <th class="fit">Fixable</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="run in shown" :key="run.scan_run_id">
          <td class="fit">
            <span class="mono-cell sm nowrap" :title="run.started_at ?? ''">{{
              lastDataAt(run.started_at)
            }}</span>
          </td>
          <td>
            <span class="mono-cell sm run-id" :title="run.scan_run_id">{{ run.scan_run_id }}</span>
          </td>
          <td class="mix-col">
            <MixBar :counts="mix(run)" :attribution="scanner" />
          </td>
          <td class="fit mono-cell sm">{{ fmt(run.images) }}</td>
          <td class="fit mono-cell sm">{{ fmt(run.findings_total) }}</td>
          <td class="fit mono-cell sm">{{ fmt(run.fixable_total) }}</td>
        </tr>
      </tbody>
    </table>
    <GridPager
        :total="runs.length"
        :page="page"
        :size="size"
        :shown="shown.length"
        :has-prev="page > 0"
        :has-next="hasNext"
        @prev="page -= 1"
        @next="page += 1"
        @update:size="setSize"
      />
  </div>
</template>

<style scoped>
.mix-col {
  width: 110px;
}
/* the full run id, ellipsized by the column instead of hand-truncated — Run owns the slack */
.run-id {
  display: block;
  max-width: 0;
  min-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

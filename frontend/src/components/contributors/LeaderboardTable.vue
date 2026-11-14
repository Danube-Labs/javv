<script setup lang="ts">
/**
 * The contributors leaderboard (M9d slice 3; prototype table, structure-only onto the shared
 * table template + GridPager). Rows are the server's ≤100-actor board, ordered by resolved
 * (viewModel.sortBoard); pages are display slices of that answer — no client arithmetic beyond
 * slicing and the by_action reads. Severity-mix / pace columns are trimmed (not on the wire).
 * At the board cap the header says so.
 */
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import SlaPctChip from '@/components/chips/SlaPctChip.vue'
import ContributorIdentity from '@/components/contributors/ContributorIdentity.vue'
import GridPager from '@/components/findings/GridPager.vue'
import { usePagedSlice } from '@/composables/usePagedSlice'
import { ackOf, fmtMedian, resolvedOf, sortBoard, type BoardRow } from '@/contributors/viewModel'
import { fmt } from '@/lib/format'

const props = defineProps<{
  rows: BoardRow[]
  /** the terms-agg board size — rows.length === cap means "there may be a tail" */
  cap: number
}>()

const ordered = computed(() => sortBoard(props.rows))

const { page, size, shown, hasNext, setSize } = usePagedSlice(() => ordered.value)
const atCap = computed(() => props.rows.length >= props.cap)

</script>

<template>
  <div class="tbl-wrap">
    <table class="tbl tbl-dense tbl-hover">
      <thead>
        <tr>
          <th class="fit">#</th>
          <th>Person{{ atCap ? ` · top ${cap}` : '' }}</th>
          <th class="r fit">Resolved</th>
          <th class="r fit">Ack.</th>
          <th class="r fit">Actions</th>
          <th class="r fit">Median</th>
          <th class="r fit">SLA</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in shown" :key="row.actor">
          <td class="fit rank-cell mono-cell sm">{{ page * size + i + 1 }}</td>
          <td>
            <!-- the board is derived from the audit trail — the person links to their rows -->
            <RouterLink
              class="lb-link"
              :to="{ name: 'audit', query: { actor: row.actor } }"
              :title="`${row.actor}'s actions in the audit log`"
            >
              <ContributorIdentity
                :actor="row.actor"
                :sub="`${fmt(row.handled)} handled`"
                :size="30"
              />
            </RouterLink>
          </td>
          <td class="r fit mono-cell sm strong">{{ fmt(resolvedOf(row)) }}</td>
          <td class="r fit mono-cell sm">{{ fmt(ackOf(row)) }}</td>
          <td class="r fit mono-cell sm">{{ fmt(row.actions) }}</td>
          <td class="r fit mono-cell sm">{{ fmtMedian(row.median_ttr_seconds) }}</td>
          <td class="r fit"><SlaPctChip :pct="row.sla_hit_pct" /></td>
        </tr>
      </tbody>
    </table>
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
  </div>
</template>

<style scoped>
/* person link — wash + name underline on hover (feedback mandatory) */
.lb-link {
  display: inline-flex;
  color: inherit;
  text-decoration: none;
  border-radius: var(--r-sm);
  padding: 2px 6px 2px 2px;
  transition: background var(--dur-quick);
}
.lb-link:hover {
  background: var(--control-hover-bg);
}
.lb-link:hover :deep(.cid-name) {
  text-decoration: underline;
}
.lb-link:active {
  background: var(--control-active-bg);
}
.lb-link:focus-visible {
  outline: var(--focus-ring);
  outline-offset: -2px;
}
.rank-cell {
  color: var(--muted);
  font-weight: 700;
}
</style>

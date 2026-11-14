<script setup lang="ts">
/**
 * Affected components table (issue 434 refresh): every occurrence of the CVE across the last
 * committed inventory — one row per image + package, scanners listed, never merged. Truncation
 * is said out loud (accurate data), never silently. Kit skin + DetailCard chrome. The Paths
 * column (issue 1077) gives one number for each finding of the row, and a row with a path opens
 * to list the paths under it.
 */
import { reactive, watch } from 'vue'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import DetailCard from '@/components/finding/DetailCard.vue'
import FindingPaths from '@/components/finding/FindingPaths.vue'
import PathsCount from '@/components/finding/PathsCount.vue'
import GridPager from '@/components/findings/GridPager.vue'
import { usePagedSlice } from '@/composables/usePagedSlice'
import type { AffectedComponentRow } from '@/findings/detailViewModel'

const props = defineProps<{
  affected: AffectedComponentRow[]
  truncated: boolean
  /** the occurrences read was refused: say so, never "none" (issue 833, F2) */
  failed?: boolean
}>()

/* display slices through the shared GridPager — a 100-image CVE pages instead of walling */
const { page, size, shown, hasNext, setSize } = usePagedSlice(() => props.affected)

const rowKey = (a: AffectedComponentRow) => `${a.image}|${a.packageName}|${a.current}|${a.fixed}`
/* the rows the user opened; a new read (another CVE, another T) or another page of the card
   starts with all of them closed, as the image table does */
const open = reactive(new Set<string>())
watch([() => props.affected, page, size], () => open.clear())
function toggle(key: string) {
  if (open.has(key)) open.delete(key)
  else open.add(key)
}
/* the id of the row under a row, for aria-controls; the index keeps it a valid, unique id */
const pathsId = (i: number) => `affected-paths-${page.value}-${i}`
</script>

<template>
  <DetailCard
    title="Affected components"
    sub="across the last committed inventory · one row for each image and package, with its scanners"
    flush
  >
    <template #title>
      Affected components <span class="count-badge">{{ failed ? '-' : `${affected.length}${truncated ? '+' : ''}` }}</span>
    </template>
    <div class="tbl-wrap">
      <table class="tbl tbl-dense">
        <thead>
          <tr><th>Image</th><th>Namespace</th><th>Package</th><th>Current</th><th>Fixed</th><th>Paths</th><th>Scanners</th></tr>
        </thead>
        <tbody>
          <tr v-if="affected.length === 0"><td colspan="7" class="empty-row">{{ failed ? 'Could not be loaded.' : 'No occurrences returned.' }}</td></tr>
          <template v-for="(a, i) in shown" :key="rowKey(a)">
            <tr :class="{ 'row-open': open.has(rowKey(a)) }">
              <td class="mono-cell strong">{{ a.image }}</td>
              <td class="mono-cell sm"><template v-if="a.namespaces.length">{{ a.namespaces.join(', ') }}</template><span v-else class="muted-dash">-</span></td>
              <td class="mono-cell sm">{{ a.packageName }}</td>
              <td class="mono-cell sm"><template v-if="a.current != null">{{ a.current }}</template><span v-else class="muted-dash">-</span></td>
              <td class="mono-cell sm" :class="{ 'no-fix': !a.fixed }">{{ a.fixed ?? 'no fix' }}</td>
              <td class="nowrap">
                <PathsCount :entries="a.paths" :open="open.has(rowKey(a))" :controls="pathsId(i)" @toggle="toggle(rowKey(a))" />
              </td>
              <td><ScannerTag v-for="s in a.scanners" :key="s" :name="s" class="scn-gap" /></td>
            </tr>
            <tr v-if="open.has(rowKey(a))" :id="pathsId(i)">
              <td colspan="7" class="paths-cell">
                <FindingPaths :entries="a.paths" :package-name="a.packageName" :version="a.current" />
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <GridPager
      :total="affected.length"
      :page="page"
      :size="size"
      :shown="shown.length"
      :has-prev="page > 0"
      :has-next="hasNext"
      @prev="page -= 1"
      @next="page += 1"
      @update:size="setSize"
    />
    <div class="card-notes">
      <p v-if="truncated" class="evidence-note">
        Showing the first {{ affected.length }} components. More exist. Narrow via the
        Findings grid (search the CVE id).
      </p>
      <p class="evidence-note">
        A package listed by one scanner only, or twice with different versions, is a scanner
        disagreement, not a clean bill. Workload names land with the envelope (v1.1).
      </p>
    </div>
  </DetailCard>
</template>

<style scoped>
.evidence-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
.count-badge {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 400;
  color: var(--soft);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-chip);
  padding: 2px 7px;
  margin-left: 6px;
  vertical-align: 2px;
}
.no-fix {
  color: var(--soft);
  font-style: italic;
}
.scn-gap {
  margin-right: 4px;
}
/* the opened row and its paths read as one block */
.row-open td {
  border-bottom-color: transparent;
}
.tbl.tbl .paths-cell {
  padding: 0;
}
/* below about 1100px the table is wider than its card and scrolls: the list keeps to the part in
   view, wherever the table is scrolled */
.tbl-wrap {
  container-type: inline-size;
}
.paths-cell :deep(.paths-panel) {
  position: sticky;
  left: 0;
  box-sizing: border-box;
  width: 100cqw;
}
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 28px 12px;
}
</style>

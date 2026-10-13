<script setup lang="ts">
/**
 * Affected components table (issue 434 refresh): every occurrence of the CVE across the last
 * committed inventory — one row per image + package, scanners listed, never merged. Truncation
 * is said out loud (accurate data), never silently. Kit skin + DetailCard chrome.
 */
import ScannerTag from '@/components/chips/ScannerTag.vue'
import DetailCard from '@/components/finding/DetailCard.vue'
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
</script>

<template>
  <DetailCard
    title="Affected components"
    sub="across the last committed inventory · one row per image + package, scanners listed, never merged"
    flush
  >
    <template #title>
      Affected components <span class="count-badge">{{ failed ? '-' : `${affected.length}${truncated ? '+' : ''}` }}</span>
    </template>
    <div class="tbl-wrap">
      <table class="tbl tbl-dense">
        <thead>
          <tr><th>Image</th><th>Namespace</th><th>Package</th><th>Current</th><th>Fixed</th><th>Scanners</th></tr>
        </thead>
        <tbody>
          <tr v-if="affected.length === 0"><td colspan="6" class="empty-row">{{ failed ? 'Could not be loaded.' : 'No occurrences returned.' }}</td></tr>
          <tr v-for="a in shown" :key="`${a.image}|${a.packageName}|${a.current}|${a.fixed}`">
            <td class="mono-cell strong">{{ a.image }}</td>
            <td class="mono-cell sm"><template v-if="a.namespaces.length">{{ a.namespaces.join(', ') }}</template><span v-else class="muted-dash">-</span></td>
            <td class="mono-cell sm">{{ a.packageName }}</td>
            <td class="mono-cell sm"><template v-if="a.current != null">{{ a.current }}</template><span v-else class="muted-dash">-</span></td>
            <td class="mono-cell sm" :class="{ 'no-fix': !a.fixed }">{{ a.fixed ?? 'no fix' }}</td>
            <td><ScannerTag v-for="s in a.scanners" :key="s" :name="s" class="scn-gap" /></td>
          </tr>
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
.empty-row {
  text-align: center;
  color: var(--soft);
  padding: 28px 12px;
}
</style>

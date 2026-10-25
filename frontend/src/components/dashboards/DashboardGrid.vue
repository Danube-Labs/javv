<script setup lang="ts">
/**
 * A saved dashboard's panels on a CSS grid (issue 440, decision Q5): two columns and rows of
 * 40 px, the cells of the edit grid, with no layout library on the read page. Each cell keeps
 * a 15 px margin inside it, the gridstack margin, so a layout reads the same in both modes; the
 * cell scrolls a panel taller than its slot, and its margin leaves room for the card's shadow.
 * Below the shared breakpoint the panels stack in one column in reading order (y, then x), each
 * as tall as its content.
 */
import { computed } from 'vue'

import type { DashboardPanel } from '@/api/generated'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import PanelFrame from '@/components/dashboards/PanelFrame.vue'
import { cellStyle, isPinned, panelPropsCache, placePanels } from '@/dashboards/layout'
import type { ScannerLens } from '@/lib/scannerLens'

const props = defineProps<{
  panels: readonly DashboardPanel[]
  clusterId: string
  t: string | null
  windowDays: number
  scanner: ScannerLens
}>()

const placed = computed(() => placePanels(props.panels))

const propsFor = panelPropsCache()
const panelProps = computed(() => placed.value.map((p) => propsFor(`${p.stored.x}-${p.stored.y}`, p, props)))
</script>

<template>
  <div class="dash-grid">
    <div
      v-for="(p, i) in placed"
      :key="`${p.stored.x}-${p.stored.y}`"
      class="dash-cell"
      :style="cellStyle(p)"
      :data-panel="p.panel.id"
    >
      <span v-if="p.panel.usesScanner && isPinned(p.stored)" class="dash-pin">
        <ScannerTag :name="String(p.stored.scanner)" /> pinned
      </span>
      <PanelFrame v-if="p.panel.framed" :title="p.panel.name" :line="p.panel.line">
        <component :is="p.panel.component" v-bind="panelProps[i]" />
      </PanelFrame>
      <component :is="p.panel.component" v-else v-bind="panelProps[i]" />
    </div>
  </div>
</template>

<style scoped>
.dash-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 40px;
  /* the cells' own margin lines their cards up with the page edge */
  margin: 0 -15px;
}
.dash-cell {
  grid-column: var(--col) / span var(--cols);
  grid-row: var(--row) / span var(--rows);
  position: relative;
  min-width: 0;
  padding: 15px;
  overflow: auto;
}
/* in the cell's top margin, over the card's top right corner */
.dash-pin {
  position: absolute;
  top: 0;
  right: 30px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 6px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-chip);
  font-size: var(--text-sm);
  color: var(--soft);
}
/* the shared breakpoint (DESIGN.md §4): one column, and each panel takes the height of its
   content, since a narrow panel wraps (the findings summary's bands go to three rows) */
@media (max-width: 1100px) {
  .dash-grid {
    grid-template-columns: minmax(0, 1fr);
    grid-auto-rows: auto;
  }
  .dash-cell {
    grid-column: 1;
    grid-row: auto;
    overflow: visible;
  }
}
</style>

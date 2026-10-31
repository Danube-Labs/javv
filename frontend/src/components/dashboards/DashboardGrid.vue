<script setup lang="ts">
/**
 * A saved dashboard's panels on the read page, in the blocks of `pageBlocks`: a Full panel by
 * itself, or two columns of Half panels. Each panel is as tall as its content and the gaps are the
 * page's grid gap in both directions, so nothing scrolls inside a panel and each card draws its
 * whole shadow. Below the shared breakpoint the columns stack in one column, in the same order.
 */
import { computed } from 'vue'

import type { DashboardPanel } from '@/api/generated'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import PanelFiltersButton from '@/components/dashboards/PanelFiltersButton.vue'
import PanelFrame from '@/components/dashboards/PanelFrame.vue'
import { isPinned, pageBlocks, panelPropsCache, placePanels, type PageBlock, type PlacedPanel } from '@/dashboards/layout'
import type { ScannerLens } from '@/lib/scannerLens'

const props = defineProps<{
  panels: readonly DashboardPanel[]
  clusterId: string
  t: string | null
  windowDays: number
  scanner: ScannerLens
}>()

const blocks = computed(() => pageBlocks(placePanels(props.panels)))

const propsFor = panelPropsCache()
const place = (p: PlacedPanel) => `${p.stored.x}-${p.stored.y}`
const panelProps = (p: PlacedPanel) => propsFor(place(p), p, props)
const blockKey = (b: PageBlock) => place(b.columns.flat()[0]!)
const pinnedOf = (p: PlacedPanel) => (p.panel.usesScanner && isPinned(p.stored) ? (p.stored.scanner as 'trivy' | 'grype') : null)
</script>

<template>
  <div class="dash-grid">
    <div v-for="b in blocks" :key="blockKey(b)" class="dash-block" :class="{ 'dash-block--full': b.full }">
      <div v-for="(col, ci) in b.columns" :key="ci" class="dash-stack">
        <div v-for="p in col" :key="place(p)" class="dash-cell" :data-panel="p.panel.id">
          <span class="dash-corner">
            <span v-if="pinnedOf(p)" class="dash-pin">
              <ScannerTag :name="String(pinnedOf(p))" /> pinned
            </span>
            <PanelFiltersButton
              v-if="p.panel.takesFilters"
              :filters="p.stored.filters"
              :panel-name="p.panel.name"
              :pinned="pinnedOf(p)"
            />
          </span>
          <PanelFrame v-if="p.panel.framed" :title="p.panel.name" :line="p.panel.line">
            <component :is="p.panel.component" v-bind="panelProps(p)" />
          </PanelFrame>
          <component :is="p.panel.component" v-else v-bind="panelProps(p)" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dash-grid,
.dash-stack {
  display: flex;
  flex-direction: column;
  gap: var(--grid-gap);
}
.dash-block {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--grid-gap);
  align-items: start;
}
.dash-block--full {
  grid-template-columns: minmax(0, 1fr);
}
/* min-width 0: an ECharts canvas's drawn width would otherwise pin the column (OverviewView) */
.dash-stack,
.dash-cell {
  min-width: 0;
}
/* the Findings summary sets its bands by the width of its cell, not of the screen */
.dash-cell {
  position: relative;
  container-type: inline-size;
}
/* over the card's top right corner, half in the gap above it: the pinned scanner tag and the
   filters button of the panel (issue 999). The row is 24px tall: at -13px it ends 3px under the
   panel above and 4px over a button in the card's head, which starts 15px down */
.dash-corner {
  position: absolute;
  top: -13px;
  right: 15px;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
/* the height of a mini UiButton, so the tag and the filters button make one row */
.dash-pin {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  box-sizing: border-box;
  min-height: 24px;
  padding: 0 6px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-chip);
  font-size: var(--text-sm);
  color: var(--soft);
}
/* the shared breakpoint (DESIGN.md §4): one column, left column first in each block */
@media (max-width: 1100px) {
  .dash-block {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

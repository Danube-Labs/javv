<script setup lang="ts">
/**
 * A dashboard's panels in edit mode (issue 440, decision Q5): gridstack in `top` mode, two
 * columns, rows of 40 px and a 15 px margin, the cells of the read page, with no resize (R10).
 * Only this component imports gridstack, and the page loads it only in edit mode, so the read
 * page loads no layout library. gridstack owns where a panel is on the screen and the page owns
 * the panels: a drop sends the new places up, and a panel that the page adds, changes or removes
 * goes to gridstack here. The Move tab is the one drag handle, and no key moves a panel (R11).
 */
import 'gridstack/dist/gridstack.min.css'
import { GridStack, type GridStackNode } from 'gridstack'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import PanelFrame from '@/components/dashboards/PanelFrame.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import type { DraftPanel, PanelPlace } from '@/dashboards/edit'
import { isPinned, panelPropsCache, placeOne, type PlacedPanel } from '@/dashboards/layout'
import type { ScannerLens } from '@/lib/scannerLens'

const props = defineProps<{
  panels: readonly DraftPanel[]
  clusterId: string
  t: string | null
  windowDays: number
  scanner: ScannerLens
}>()
const emit = defineEmits<{
  /** the places as gridstack first lays them out: `top` mode moves a panel up into empty space */
  ready: [places: PanelPlace[]]
  moved: [places: PanelPlace[]]
  settings: [key: string]
  remove: [key: string]
}>()

const placed = computed(() =>
  props.panels.map(placeOne).filter((p): p is PlacedPanel & { stored: DraftPanel } => p !== null),
)
const propsFor = panelPropsCache()
const panelProps = computed(() => placed.value.map((p) => propsFor(p.stored.key, p, props)))

const gridEl = ref<HTMLElement | null>(null)
let grid: GridStack | null = null

const placesOf = (nodes: readonly GridStackNode[]): PanelPlace[] =>
  nodes.map((n) => ({ key: String(n.id), x: n.x ?? 0, y: n.y ?? 0 }))

onMounted(() => {
  if (!gridEl.value) return
  const g = GridStack.init(
    {
      column: 2,
      cellHeight: 40,
      margin: 15,
      mode: 'top',
      disableResize: true,
      // the panels jump to their new places: a sliding panel is a layout animation (DESIGN.md §9)
      animate: false,
      // the handle is a button, which gridstack refuses by default (gridstack issue 2703)
      draggable: { handle: '.dash-move', cancel: 'input,textarea,select,option' },
    },
    gridEl.value,
  )
  if (!g) return
  g.on('change', (_event, nodes) => emit('moved', placesOf(nodes)))
  grid = g
  emit('ready', placesOf(g.engine.nodes))
})
onBeforeUnmount(() => grid?.destroy(false))

/** After the page renders a change of its panels, give gridstack the panels it does not have,
 * take away the ones that are gone, and apply a new width or height. */
watch(
  () => placed.value.map((p) => `${p.stored.key}:${p.stored.x}:${p.stored.w}:${p.rows}`).join(','),
  () => {
    if (!grid || !gridEl.value) return
    const nodes = new Map(grid.engine.nodes.map((n) => [String(n.id), n]))
    const keys = new Set(placed.value.map((p) => p.stored.key))
    grid.batchUpdate()
    for (const [key, node] of nodes) if (!keys.has(key) && node.el) grid.removeWidget(node.el, false)
    for (const p of placed.value) {
      const node = nodes.get(p.stored.key)
      if (!node) {
        const el = gridEl.value.querySelector<HTMLElement>(`[gs-id="${p.stored.key}"]`)
        if (el) grid.makeWidget(el)
      } else if (node.el && (node.w !== p.stored.w || node.h !== p.rows || node.x !== p.stored.x)) {
        grid.update(node.el, { x: p.stored.x, w: p.stored.w, h: p.rows })
      }
    }
    grid.batchUpdate(false)
    // `top` mode packs a new panel upward, and gridstack sends no change event for a node it has
    // just added, so the page takes every place from here
    emit('moved', placesOf(grid.engine.nodes))
  },
  { flush: 'post' },
)
</script>

<template>
  <div ref="gridEl" class="grid-stack dash-edit">
    <div
      v-for="(p, i) in placed"
      :key="p.stored.key"
      class="grid-stack-item"
      :gs-id="p.stored.key"
      :gs-x="p.stored.x"
      :gs-y="p.stored.y"
      :gs-w="p.stored.w"
      :gs-h="p.rows"
      :data-panel="p.panel.id"
    >
      <div class="grid-stack-item-content">
        <button type="button" class="dash-tab dash-move" :aria-label="`Move ${p.panel.name}`">
          <AppIcon name="grip" :size="13" />Move
        </button>
        <div class="dash-tab dash-tools">
          <span v-if="p.panel.usesScanner && isPinned(p.stored)" class="dash-pinned">
            <ScannerTag :name="String(p.stored.scanner)" /> pinned
          </span>
          <UiButton variant="mini" :aria-label="`Settings of ${p.panel.name}`" @click="emit('settings', p.stored.key)">
            <AppIcon name="gear" :size="12" />Settings
          </UiButton>
          <UiButton variant="mini" :aria-label="`Remove ${p.panel.name}`" @click="emit('remove', p.stored.key)">
            <AppIcon name="trash" :size="12" />
          </UiButton>
        </div>
        <div class="dash-body">
          <PanelFrame v-if="p.panel.framed" :title="p.panel.name" :line="p.panel.line">
            <component :is="p.panel.component" v-bind="panelProps[i]" />
          </PanelFrame>
          <component :is="p.panel.component" v-else v-bind="panelProps[i]" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* the grid's own margin lines the cards up with the page edge, as on the read page; the top
   padding leaves room for the first row's tabs */
.dash-edit {
  margin: 0 -15px;
  padding-top: 12px;
}
/* the tabs hang over the card's top edge, so the content box does not clip; the body under it
   scrolls a panel taller than its slot, and its own margin leaves room for the card's shadow */
.dash-edit .grid-stack-item > .grid-stack-item-content {
  overflow: visible;
}
.dash-body {
  height: calc(100% + 30px);
  margin: -15px;
  padding: 15px;
  overflow: auto;
  box-sizing: border-box;
}
.dash-tab {
  position: absolute;
  top: -27px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 27px;
  padding: 0 6px;
  background: var(--card);
  border: 1px solid var(--line);
  border-bottom: 0;
  border-radius: var(--r-sm) var(--r-sm) 0 0;
}
/* the one drag surface: grab and grabbing are the ruled cursor exception (DESIGN.md §5) */
.dash-move {
  left: 14px;
  padding: 0 10px;
  font-family: var(--font-ui);
  font-size: var(--text-control);
  font-weight: 600;
  color: var(--ink);
  cursor: grab;
  user-select: none;
  transition:
    background var(--dur-quick) var(--ease-out),
    border-color var(--dur-quick) var(--ease-out);
}
.dash-move:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.dash-move:active {
  background: var(--control-active-bg);
  cursor: grabbing;
}
.dash-move:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.dash-tools {
  right: 14px;
}
.dash-pinned {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 4px;
  font-size: var(--text-sm);
  color: var(--soft);
}
/* the drop place: the coral language of a drop target */
.dash-edit :deep(.grid-stack-placeholder > .placeholder-content) {
  background: var(--dd-on-bg);
  border: 2px dashed var(--coral);
  border-radius: var(--r);
}
/* the dragged panel lifts (the sortable grammar of Framework7: a shadow, no tilt) */
.dash-edit :deep(.ui-draggable-dragging .dash-body > *) {
  box-shadow: var(--dd-shadow);
}
</style>

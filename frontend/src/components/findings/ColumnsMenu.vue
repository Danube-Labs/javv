<script setup lang="ts">
/**
 * Column visibility + density menu (prototype filters.jsx `ColumnsMenu` + `.cols-menu`/`.seg`
 * CSS). Generic over a `cols` list so future grid screens (images, audit) reuse it — the
 * parent owns the hidden-set, density and order state (and any persistence).
 *
 * With `reorderable` (task 92), rows drag to reorder — the field-list grammar: a grip
 * handle, the dragged row dims, a coral insertion line marks the drop slot. Emits the full
 * new key order; hidden columns reorder too (their slot is kept for when they're re-shown).
 */
import { ref } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDropdown from '@/components/ui/UiDropdown.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { moveKey } from '@/system/columnOrder'

const props = withDefaults(
  defineProps<{
    cols: readonly (readonly [string, string])[]
    hidden: ReadonlySet<string>
    dense: boolean
    /** rows drag to reorder; parent passes `cols` already in display order */
    reorderable?: boolean
  }>(),
  { reorderable: false },
)

const emit = defineEmits<{
  toggleCol: [key: string]
  'update:dense': [dense: boolean]
  reorder: [keys: string[]]
}>()

const DENSITY_OPTS = [
  { value: 'compact', label: 'Compact' },
  { value: 'comfortable', label: 'Comfortable' },
] as const

/* ---- row drag (HTML5 dnd — rows are the drop slots, the grip is the affordance) ---- */
const dragKey = ref<string | null>(null)
const overIndex = ref<number | null>(null)

function onDragStart(e: DragEvent, key: string) {
  if (!props.reorderable) return
  dragKey.value = key
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', key) // Firefox needs data for the drag to start
  }
}
function onDragOver(e: DragEvent, index: number) {
  if (dragKey.value === null) return
  e.preventDefault()
  overIndex.value = index
}
function onDrop() {
  if (dragKey.value !== null && overIndex.value !== null) {
    const next = moveKey(
      props.cols.map(([key]) => key),
      dragKey.value,
      overIndex.value,
    )
    if (next) emit('reorder', next)
  }
  dragKey.value = null
  overIndex.value = null
}
function onDragEnd() {
  dragKey.value = null
  overIndex.value = null
}
</script>

<template>
  <UiDropdown class="cols-dd">
    <template #trigger="{ toggle }">
      <UiButton variant="control" @click="toggle"><AppIcon name="columns" :size="13" />Columns</UiButton>
    </template>
    <div class="dd-menu cols-menu">
      <div class="dd-head">Density</div>
      <UiSegControl
        class="density-seg"
        label="Density"
        :model-value="dense ? 'compact' : 'comfortable'"
        :options="DENSITY_OPTS"
        @update:model-value="(v) => emit('update:dense', v === 'compact')"
      />
      <div class="dd-head">Columns<span v-if="props.reorderable" class="dd-head-hint">drag to reorder</span></div>
      <button
        v-for="([key, label], index) in cols"
        :key="key"
        class="facet-row"
        :class="{
          'facet-on': !hidden.has(key),
          'row-reorderable': props.reorderable,
          'row-dragging': dragKey === key,
          'row-drop-target': dragKey !== null && dragKey !== key && overIndex === index,
        }"
        :draggable="props.reorderable"
        @click="emit('toggleCol', key)"
        @dragstart="onDragStart($event, key)"
        @dragover="onDragOver($event, index)"
        @drop.prevent="onDrop()"
        @dragend="onDragEnd()"
      >
        <AppIcon v-if="props.reorderable" name="grip" :size="12" class="row-grip" />
        <span class="facet-check" />
        <span class="facet-label">{{ label }}</span>
      </button>
    </div>
  </UiDropdown>
</template>

<style scoped>
.cols-dd {
  flex: none;
}
.dd-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  left: auto;
  z-index: 30;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--dd-shadow);
  padding: 6px;
  min-width: 230px;
}
.dd-head {
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--soft);
  padding: 8px 12px 6px;
}
.dd-head-hint {
  float: right;
  letter-spacing: 0.06em;
  color: var(--soft);
}
.density-seg {
  margin: 2px 8px 8px;
}
.facet-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 5px 8px;
  border-radius: 7px;
  text-align: left;
  color: var(--ink);
  font-size: var(--text-control);
  cursor: default;
}
.facet-row:hover {
  background: var(--panel);
}
.facet-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.row-reorderable {
  border-top: 2px solid transparent; /* reserved so the insertion line never shifts rows */
  cursor: grab; /* the ruled drag-surface exception (DESIGN.md §5) */
}
.row-reorderable:active {
  cursor: grabbing;
}
.row-grip {
  color: var(--soft);
  margin: 0 -2px;
}
.facet-row:hover .row-grip {
  color: var(--ink);
}
.row-dragging {
  opacity: 0.45;
}
.row-drop-target {
  border-top-color: var(--coral);
  border-top-left-radius: 0;
  border-top-right-radius: 0;
}
.facet-check {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1.5px solid var(--facet-check-line);
  flex: none;
  transition: 0.1s;
}
.facet-on .facet-check {
  background: var(--coral);
  border-color: var(--coral);
  box-shadow: inset 0 0 0 2px var(--card);
}
.facet-on {
  color: var(--ink);
  font-weight: 500;
}
.facet-label {
  flex: 1;
}
</style>

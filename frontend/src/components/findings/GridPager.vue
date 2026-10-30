<script setup lang="ts">
/**
 * Cursor-mode pager (prototype `Pager` + `.pager` CSS, adapted): the shipped M6 contract pages
 * by PIT cursor — prev/next over the visited stack, NO numbered jumps (bolt README 2026-07-09).
 * Total is the server's; the "showing X–Y" range is display arithmetic on server numbers only.
 */
import { computed } from 'vue'

import UiButton from '@/components/ui/UiButton.vue'
import UiSelect from '@/components/ui/UiSelect.vue'

const props = defineProps<{
  total: number
  page: number
  size: number
  shown: number
  /** the current page's read was refused: keep its range so the user knows where they are */
  failed?: boolean
  hasPrev: boolean
  hasNext: boolean
}>()

const emit = defineEmits<{ prev: []; next: []; 'update:size': [size: number] }>()

const SIZES = [10, 25, 50]
const range = computed(() => {
  const count = props.failed ? props.size : props.shown
  if (props.total === 0 || count === 0) return null
  const start = props.page * props.size + 1
  return { start, end: Math.min(start + count - 1, props.total) }
})
const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <!-- nothing to page and nowhere to go back to: the table's own empty message stands alone -->
  <div v-if="total > 0 || hasPrev" class="pager">
    <span class="pager-info">
      {{ range ? `Showing ${fmt(range.start)}–${fmt(range.end)} of ${fmt(total)}` : 'No results' }}
    </span>
    <div class="pager-right">
      <label class="pager-size">
        Rows per page
        <UiSelect small :model-value="String(size)" @update:model-value="emit('update:size', Number($event))">
          <option v-for="s in SIZES" :key="s" :value="String(s)">{{ s }}</option>
        </UiSelect>
      </label>
      <div class="pager-btns">
        <UiButton class="pager-btn" :disabled="!hasPrev" @click="emit('prev')">Prev</UiButton>
        <UiButton class="pager-btn" :disabled="!hasNext" @click="emit('next')">Next</UiButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* the in-card pager row (operator ruling 2026-07-13, on the approvals specimen): every
   GridPager sits INSIDE its table card, flush, on a quiet tint that sets it off from rows */
.pager {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 1px solid var(--line2);
  background: var(--panel);
  padding: 9px 14px;
}
.pager-info {
  font-size: var(--text-quiet-action);
  color: var(--soft);
  font-family: var(--font-mono);
}
.pager-right {
  display: flex;
  align-items: center;
  gap: 16px;
}
.pager-size {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: var(--text-sm);
  color: var(--soft);
  font-family: var(--font-mono);
}
.pager-btns {
  display: flex;
  gap: 5px;
}
.pager-btn {
  min-width: 48px;
}
</style>

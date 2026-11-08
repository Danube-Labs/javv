<script setup lang="ts">
/**
 * THE modal skeleton: backdrop + card + head/body/actions slots, carrying the ruled
 * dismiss contract (DESIGN.md §2) once — Escape, outside-click, visible ✕ — so dialogs can't
 * drift apart again. Consumers own only their body content and action buttons.
 */
import { onMounted, onUnmounted } from 'vue'

import UiCloseButton from '@/components/ui/UiCloseButton.vue'

defineProps<{ title: string; subtitle?: string; width?: number }>()
const emit = defineEmits<{ close: [] }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <!-- appear: consumers v-if the whole dialog, so the t-modal entrance plays on mount;
       close stays instant — unmount is what resets consumer form state. -->
  <Transition name="t-modal" appear>
  <div class="modal-backdrop" @click.self="emit('close')">
    <div class="modal" role="dialog" aria-modal="true" :aria-label="title" :style="{ width: `min(${width ?? 520}px, 100%)` }">
      <div class="modal-head">
        <div>
          <h3>{{ title }}</h3>
          <p v-if="subtitle" class="modal-sub">{{ subtitle }}</p>
        </div>
        <UiCloseButton class="modal-close" dark label="Close" @click="emit('close')" />
      </div>
      <div class="modal-body"><slot /></div>
      <div class="modal-actions"><slot name="actions" /></div>
    </div>
  </div>
  </Transition>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
  display: grid;
  place-items: center;
  z-index: 80;
  padding: 24px;
}
/* no border line: the shadow alone sets the window off the backdrop (operator 2026-11-07 on
   built pictures, issue 1127, D3 G). A beige line on the dark backdrop read as cheap. */
.modal {
  background: var(--card);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}
/* the slate band of the table heads and the side panel head, on every window (operator
   2026-10-29, issue 1049): one pair of tokens, so all three bands move together */
.modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
  background: var(--table-head-bg);
  color: var(--table-head-fg);
  /* the card's own radius, since the card has no border: a square corner shows a light seam */
  border-top-left-radius: var(--r);
  border-top-right-radius: var(--r);
}
.modal-head h3 {
  margin: 0;
}
.modal-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  opacity: 0.75;
}
.modal-body {
  padding: 14px 18px;
  overflow-y: auto;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px 16px;
  border-top: 1px solid var(--line2);
}
</style>

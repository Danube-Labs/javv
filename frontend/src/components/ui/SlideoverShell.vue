<script setup lang="ts">
/**
 * THE slideover skeleton (ModalShell's right-drawer sibling; ui.nuxt.com USlideover grammar
 * on JAVV tokens): backdrop + right-anchored panel + head/body slots, carrying the ruled dismiss
 * contract (DESIGN.md §2) — Escape, outside-click, visible ✕. For tall workflows that want
 * the page context to stay visible behind them (triage, future notification rail).
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
  <Transition name="t-slideover" appear>
    <div class="so-backdrop" @click.self="emit('close')">
      <div
        class="so-panel"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        :style="{ width: `min(${width ?? 440}px, 100%)` }"
      >
        <div class="so-head">
          <div>
            <h3>{{ title }}</h3>
            <p v-if="subtitle" class="so-sub">{{ subtitle }}</p>
          </div>
          <UiCloseButton class="so-close" dark label="Close" @click="emit('close')" />
        </div>
        <div class="so-body"><slot /></div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.so-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
  z-index: 80;
  display: flex;
  justify-content: flex-end;
  /* floating register (operator 2026-07-17, the framework7 float): the panel detaches from
     the screen edges instead of running flush; the backdrop itself blurs slightly so the beige
     page reads soft through the margins */
  padding: 12px;
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
.so-panel {
  /* glass register (operator 2026-07-17): semi-opaque over a backdrop blur; neutral edge —
     the beige hairline bled against the dark backdrop */
  background: var(--glass);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid var(--glass-edge);
  border-radius: var(--r);
  overflow: hidden;
  box-shadow: var(--shadow);
  height: 100%;
  display: flex;
  flex-direction: column;
}
/* the B2 slate band — same register as the table heads + triage head */
.so-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: var(--table-head-bg);
  color: var(--table-head-fg);
  flex: none;
  /* nested radius (outer − border): overflow-clipping the square head corner leaves a light
     anti-aliased seam under the panel edge — the "beige scratch" (operator, playwright zoom) */
  border-top-left-radius: calc(var(--r) - 1px);
  border-top-right-radius: calc(var(--r) - 1px);
}
.so-head h3 {
  margin: 0;
}
.so-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  opacity: 0.75;
}
.so-body {
  overflow-y: auto;
  flex: 1;
}

/* drawer motion: slide from the right; backdrop fades (transform/opacity only) */
.t-slideover-enter-active,
.t-slideover-leave-active {
  transition: opacity 0.16s ease-out;
}
.t-slideover-enter-active .so-panel,
.t-slideover-leave-active .so-panel {
  transition: transform 0.18s ease-out;
}
.t-slideover-enter-from,
.t-slideover-leave-to {
  opacity: 0;
}
.t-slideover-enter-from .so-panel,
.t-slideover-leave-to .so-panel {
  transform: translateX(24px);
}
@media (prefers-reduced-motion: reduce) {
  .t-slideover-enter-active,
  .t-slideover-leave-active,
  .t-slideover-enter-active .so-panel,
  .t-slideover-leave-active .so-panel {
    transition: none;
  }
}
</style>

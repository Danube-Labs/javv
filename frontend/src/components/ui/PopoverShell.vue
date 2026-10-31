<script setup lang="ts">
/**
 * THE popover skeleton (ModalShell's small sibling; ui.nuxt.com UPopover and the framework7
 * popover, on JAVV tokens): a card with an arrow next to the element it belongs to, so that
 * element stays in view while the user changes it. No backdrop: the page stays sharp. It
 * carries the ruled dismiss contract (DESIGN.md §2): Escape, a click outside, a visible ✕. A
 * mousedown on the trigger does not close it, so the trigger's own click decides. Focus goes
 * into the card on open and back to the trigger on close.
 */
import { nextTick, onMounted, onUnmounted, ref, useTemplateRef } from 'vue'

import { placeBeside, type Placed } from '@/lib/placeBeside'

const props = defineProps<{
  title: string
  subtitle?: string
  /** the element that the popover sits next to */
  anchor: HTMLElement
  /** the control that opened it */
  trigger?: HTMLElement | null
  width?: number
}>()
const emit = defineEmits<{ close: [] }>()

const card = useTemplateRef<HTMLElement>('card')
const place = ref<Placed>({ left: 0, top: 0, side: 'right', arrow: 16 })

function measure() {
  if (!card.value) return
  const t = props.trigger?.getBoundingClientRect()
  place.value = placeBeside(
    props.anchor.getBoundingClientRect(),
    { width: card.value.offsetWidth, height: card.value.offsetHeight },
    { width: window.innerWidth, height: window.innerHeight },
    t ? { x: t.left + t.width / 2, y: t.top + t.height / 2 } : undefined,
  )
}
// a card whose content grows (a filter row more) goes to its place again, so it stays inside the
// screen; the test DOM has no ResizeObserver
const grown = typeof ResizeObserver === 'function' ? new ResizeObserver(() => measure()) : null
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
function onDown(e: MouseEvent) {
  const target = e.target as Node
  if (card.value?.contains(target) || props.trigger?.contains(target)) return
  emit('close')
}

onMounted(async () => {
  document.addEventListener('keydown', onKey)
  document.addEventListener('mousedown', onDown)
  window.addEventListener('resize', measure)
  window.addEventListener('scroll', measure, true)
  await nextTick()
  measure()
  if (card.value) grown?.observe(card.value)
  card.value?.focus()
})
onUnmounted(() => {
  grown?.disconnect()
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('mousedown', onDown)
  window.removeEventListener('resize', measure)
  window.removeEventListener('scroll', measure, true)
  if (props.trigger?.isConnected) props.trigger.focus()
})
</script>

<template>
  <Transition name="t-pop" appear>
    <div
      ref="card"
      class="pop"
      :class="`pop-${place.side}`"
      role="dialog"
      :aria-label="subtitle ? `${title}: ${subtitle}` : title"
      tabindex="-1"
      :style="{
        width: `${width ?? 360}px`,
        left: `${place.left}px`,
        top: `${place.top}px`,
        '--pop-arrow': `${place.arrow}px`,
      }"
    >
      <div class="pop-head">
        <div>
          <h3>{{ title }}</h3>
          <p v-if="subtitle" class="pop-sub">{{ subtitle }}</p>
        </div>
        <button type="button" class="modal-close" aria-label="Close" @click="emit('close')">✕</button>
      </div>
      <div class="pop-body"><slot /></div>
    </div>
  </Transition>
</template>

<style scoped>
.pop {
  position: fixed;
  z-index: 70;
  max-width: calc(100vw - 24px);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--dd-shadow);
}
.pop:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 2px;
}
/* the arrow points at the trigger: a square turned on the edge that faces it */
.pop::before {
  content: '';
  position: absolute;
  width: 12px;
  height: 12px;
  background: var(--card);
  transform: rotate(45deg);
}
.pop-right::before {
  left: -7px;
  top: calc(var(--pop-arrow) - 6px);
  border-left: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.pop-left::before {
  right: -7px;
  top: calc(var(--pop-arrow) - 6px);
  border-right: 1px solid var(--line);
  border-top: 1px solid var(--line);
}
.pop-below::before {
  top: -7px;
  left: calc(var(--pop-arrow) - 6px);
  border-left: 1px solid var(--line);
  border-top: 1px solid var(--line);
}
.pop-above::before {
  bottom: -7px;
  left: calc(var(--pop-arrow) - 6px);
  border-right: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.pop-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px 10px 16px;
  border-bottom: 1px solid var(--line2);
}
.pop-head h3 {
  margin: 0;
}
.pop-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.pop-body {
  padding: 14px 16px 16px;
}
</style>

<script setup lang="ts">
/**
 * THE popover skeleton (ModalShell's small sibling; ui.nuxt.com UPopover and the framework7
 * popover, on JAVV tokens): a card with an arrow next to the element it belongs to, so that
 * element stays in view while the user changes it. No backdrop: the page stays sharp. `band` gives
 * it the dark head of a window, and the arrow takes that color when it points from the head. It
 * carries the ruled dismiss contract (DESIGN.md §2): Escape, a click outside, a visible ✕. A
 * mousedown on the trigger does not close it, so the trigger's own click decides. Focus goes
 * into the card on open and back to the trigger on close.
 */
import { nextTick, onMounted, onUnmounted, ref, useTemplateRef } from 'vue'

import UiCloseButton from '@/components/ui/UiCloseButton.vue'
import { arrowOnHead, placeBeside, type Placed } from '@/lib/placeBeside'

const props = defineProps<{
  title: string
  subtitle?: string
  /** the element that the popover sits next to */
  anchor: HTMLElement
  /** the control that opened it */
  trigger?: HTMLElement | null
  width?: number
  /** the dark head of the window heads (issue 1205) */
  band?: boolean
  /** with no room on a side, go under the whole anchor, not over its top edge (issue 1205) */
  under?: boolean
}>()
const emit = defineEmits<{ close: [] }>()

const card = useTemplateRef<HTMLElement>('card')
const place = ref<Placed>({ left: 0, top: 0, side: 'right', arrow: 16 })
const headHeight = ref(0)

function measure() {
  if (!card.value) return
  const t = props.trigger?.getBoundingClientRect()
  place.value = placeBeside(
    props.anchor.getBoundingClientRect(),
    { width: card.value.offsetWidth, height: card.value.offsetHeight },
    { width: window.innerWidth, height: window.innerHeight },
    t ? { x: t.left + t.width / 2, y: t.top + t.height / 2 } : undefined,
    props.under,
  )
  headHeight.value = card.value.querySelector<HTMLElement>('.pop-head')?.offsetHeight ?? 0
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
      :class="[`pop-${place.side}`, { 'pop-arrow-band': band && arrowOnHead(place, headHeight) }]"
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
      <div class="pop-head" :class="{ 'pop-head--band': band }">
        <div>
          <h3>{{ title }}</h3>
          <p v-if="subtitle" class="pop-sub">{{ subtitle }}</p>
        </div>
        <UiCloseButton class="modal-close" label="Close" :dark="band" @click="emit('close')" />
      </div>
      <div class="pop-body"><slot /></div>
    </div>
  </Transition>
</template>

<style scoped>
/* no border line: the drop shadow is the edge of the card and of its arrow (issue 1240). A filter
   makes the card the box of any fixed element inside it, so no window opens from inside a popover */
.pop {
  position: fixed;
  z-index: 70;
  max-width: calc(100vw - 24px);
  background: var(--card);
  border-radius: var(--r);
  filter: var(--pop-drop);
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
  left: -6px;
  top: calc(var(--pop-arrow) - 6px);
}
.pop-left::before {
  right: -6px;
  top: calc(var(--pop-arrow) - 6px);
}
.pop-below::before {
  top: -6px;
  left: calc(var(--pop-arrow) - 6px);
}
.pop-above::before {
  bottom: -6px;
  left: calc(var(--pop-arrow) - 6px);
}
.pop-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px 10px 16px;
  border-bottom: 1px solid var(--line2);
}
.pop-arrow-band::before {
  background: var(--table-head-bg);
}
/* the dark head of a window (ModalShell): the card's own radius, so no light seam shows */
.pop-head--band {
  background: var(--table-head-bg);
  color: var(--table-head-fg);
  border-bottom-color: var(--table-head-bg);
  border-top-left-radius: var(--r);
  border-top-right-radius: var(--r);
}
.pop-head--band .pop-sub {
  color: inherit;
  opacity: 0.75;
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

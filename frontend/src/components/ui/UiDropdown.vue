<script setup lang="ts">
/**
 * THE dropdown behavior shell (DESIGN.md §2 dismiss contract): owns open state,
 * outside-mousedown and document-level Escape, the relative anchor, and the open/close
 * motion (t-pop — every menu animates because every menu routes through here). A menu with the
 * dark head of a window asks for `t-pour`, the genie motion of the popovers (issue 1240).
 * Consumers own the trigger (slot `trigger`, given `open`/`toggle`/`close`) and the menu
 * markup (default slot, given `close`, single root) — positioning and styling stay theirs.
 * `closed` fires after the leave transition — the hook for teardown that must not be
 * visible mid-fade (e.g. FilterBar's editor reset).
 */
import { onMounted, onUnmounted, useTemplateRef } from 'vue'

const open = defineModel<boolean>('open', { default: false })
const props = withDefaults(defineProps<{ motion?: 't-pop' | 't-pour' }>(), { motion: 't-pop' })
const emit = defineEmits<{ closed: [] }>()
const wrap = useTemplateRef<HTMLElement>('wrap')

function toggle() {
  open.value = !open.value
}
function close() {
  open.value = false
}
function onDocMousedown(e: MouseEvent) {
  if (open.value && wrap.value && !wrap.value.contains(e.target as Node)) close()
}
function onDocKeydown(e: KeyboardEvent) {
  if (open.value && e.key === 'Escape') close()
}
onMounted(() => {
  document.addEventListener('mousedown', onDocMousedown)
  document.addEventListener('keydown', onDocKeydown)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onDocMousedown)
  document.removeEventListener('keydown', onDocKeydown)
})
</script>

<template>
  <div ref="wrap" class="ui-dd">
    <slot name="trigger" :open="open" :toggle="toggle" :close="close" />
    <Transition :name="props.motion" @after-leave="emit('closed')">
      <slot v-if="open" :close="close" />
    </Transition>
  </div>
</template>

<style scoped>
.ui-dd {
  position: relative;
}
</style>

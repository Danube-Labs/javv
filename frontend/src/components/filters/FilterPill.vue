<script setup lang="ts">
/**
 * One active filter in the filter bar (prototype filters.jsx `.fpill`): the field, the op words
 * and the values. A click opens the field's edit box; on a negatable field the op words switch
 * include and exclude; the ✕ clears the field. The pill is a frame of separate buttons, since a
 * button inside a button is not valid HTML and the keyboard could not reach the inner ones: the
 * field button covers the pill with its ::after, as a clickable card does (DESIGN.md § 5), and
 * the op toggle and the ✕ sit above that layer (issue 1140).
 */
import { computed } from 'vue'

import UiCloseButton from '@/components/ui/UiCloseButton.vue'
import { isNegatable, valueLabel, type FilterField } from '@/filters/fields.config'
import type { FilterMode } from '@/stores/filters'

const props = defineProps<{ field: FilterField; values: readonly string[]; mode: FilterMode }>()
const emit = defineEmits<{ open: []; toggleMode: []; clear: [] }>()

const labels = computed(() => props.values.map((v) => valueLabel(props.field, v)))
const opText = computed(() => {
  const many = props.values.length > 1
  return props.mode === 'not' ? (many ? 'is none of' : 'is not') : many ? 'is one of' : 'is'
})
const shown = computed(() =>
  labels.value.length <= 2
    ? labels.value.join(', ')
    : `${labels.value.slice(0, 2).join(', ')} +${labels.value.length - 2}`,
)
</script>

<template>
  <div class="fpill" :class="{ 'fpill-not': mode === 'not' }">
    <button
      type="button"
      class="fpill-open fpill-field"
      :aria-label="`Edit the filter ${field.label}: ${opText} ${labels.join(', ')}`"
      @click="emit('open')"
    >
      {{ field.label }}
    </button>
    <!-- ruled NOT-pill (issue 349, operator 2026-07-17): hollow body, ONLY the op words in
         red; on a negatable field the op word is the include⇄exclude toggle -->
    <button
      v-if="isNegatable(field)"
      type="button"
      class="fpill-op fpill-op-btn"
      :aria-label="`Switch to ${mode === 'not' ? 'include' : 'exclude'}`"
      :title="mode === 'not' ? 'Click to include' : 'Click to exclude'"
      @click="emit('toggleMode')"
    >
      {{ opText }}
    </button>
    <span v-else class="fpill-op">{{ opText }}</span>
    <!-- a long image repo hides the "+N"; the title holds every value -->
    <span class="fpill-vals" :title="labels.join(', ')">{{ shown }}</span>
    <UiCloseButton class="fpill-x" small :label="`Clear ${field.label}`" @click="emit('clear')" />
  </div>
</template>

<style scoped>
.fpill {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  /* control register (operator, 2026-07-17): the band's controls share one height — the
     28px pills read as undersized next to every neighboring control */
  height: 38px;
  background: var(--card);
  border: 1px solid var(--fpill-line);
  border-radius: var(--r-sm);
  padding: 0 6px 0 10px;
  font-size: var(--text-control);
  color: var(--ink);
  box-shadow: var(--shadow);
  cursor: default;
}
.fpill:hover {
  border-color: var(--coral);
}
.fpill-open {
  border: 0;
  background: transparent;
  padding: 0;
  font: inherit;
  color: inherit;
  cursor: default;
}
/* the whole pill opens the field; the ring goes round the pill, not round the label */
.fpill-open::after {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: var(--r-sm);
}
.fpill-open:focus-visible {
  outline: none;
}
.fpill-open:focus-visible::after {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.fpill-op-btn,
.fpill-x {
  position: relative;
  z-index: 1;
}
.fpill-field {
  font-weight: 600;
}
.fpill-op {
  color: var(--soft);
  font-style: italic;
  font-size: var(--text-sm);
}
.fpill-vals {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--coral-text);
  max-width: 230px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* the NOT-pill (issue 349, ruled 2026-07-17 on built specimens): the include pill is FILLED
   (card on beige), the exclude pill is HOLLOW — fill/outline duality — and ONLY the op words
   carry the red; the rest of the pill stays in the quiet register */
.fpill-not {
  background: transparent;
  border: 1.5px solid var(--fpill-line);
  box-shadow: none;
}
.fpill-not .fpill-op {
  color: var(--fpill-not-op);
  font-weight: 600;
}
/* the op word doubles as the include⇄exclude toggle on negatable fields */
.fpill-op-btn {
  border: 0;
  background: transparent;
  font-family: inherit;
  border-radius: 4px;
  padding: 1px 3px;
  margin: -1px -3px;
  cursor: default;
}
.fpill-op-btn:hover {
  background: var(--fpill-x-hover-bg);
}
</style>

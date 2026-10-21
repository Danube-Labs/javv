<script setup lang="ts">
/**
 * One active filter in the filter bar (prototype filters.jsx `.fpill`): the field, the op words
 * and the values. A click opens the field's edit box; on a negatable field the op words switch
 * include and exclude; the × clears the field.
 */
import { computed } from 'vue'

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
  <button class="fpill" :class="{ 'fpill-not': mode === 'not' }" @click="emit('open')">
    <span class="fpill-field">{{ field.label }}</span>
    <!-- ruled NOT-pill (issue 349, operator 2026-07-17): hollow body, ONLY the op words in
         red; on a negatable field the op word is the include⇄exclude toggle -->
    <span
      v-if="isNegatable(field)"
      class="fpill-op fpill-op-btn"
      role="button"
      :aria-label="`Switch to ${mode === 'not' ? 'include' : 'exclude'}`"
      :title="mode === 'not' ? 'Click to include' : 'Click to exclude'"
      @click.stop="emit('toggleMode')"
      >{{ opText }}</span
    >
    <span v-else class="fpill-op">{{ opText }}</span>
    <!-- a long image repo hides the "+N"; the title holds every value -->
    <span class="fpill-vals" :title="labels.join(', ')">{{ shown }}</span>
    <span class="fpill-x" role="button" :aria-label="`Clear ${field.label}`" @click.stop="emit('clear')"
      >×</span
    >
  </button>
</template>

<style scoped>
.fpill {
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
.fpill:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
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
.fpill-x {
  display: grid;
  place-items: center;
  width: 17px;
  height: 17px;
  border-radius: 5px;
  color: var(--soft);
  font-size: var(--text-card-title);
  line-height: 1;
}
.fpill-x:hover {
  background: var(--fpill-x-hover-bg);
  color: var(--coral-text);
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
  border-radius: 4px;
  padding: 1px 3px;
  margin: -1px -3px;
}
.fpill-op-btn:hover {
  background: var(--fpill-x-hover-bg);
}
</style>

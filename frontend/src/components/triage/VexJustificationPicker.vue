<script setup lang="ts">
/**
 * CISA-five justification chips (prototype `.vex-chips` on tokens), shown iff the target state
 * is not_affected. "False positive" is not a state — it's the mapping tag on the two
 * component/code-not-present chips (FR-7).
 */
import { CISA_JUSTIFICATIONS } from '@/findings/triageRules'

defineProps<{ selected: string | null; disabled?: boolean }>()
const emit = defineEmits<{ select: [id: string] }>()
</script>

<template>
  <div class="vex-chips" role="radiogroup" aria-label="Reason for Not affected">
    <button
      v-for="j in CISA_JUSTIFICATIONS"
      :key="j.id"
      type="button"
      role="radio"
      :aria-checked="selected === j.id"
      :disabled="disabled"
      class="vex-chip"
      :class="{ 'vex-chip-on': selected === j.id }"
      @click="emit('select', j.id)"
    >
      <span class="vex-chip-label">{{ j.label }}</span>
      <span class="vex-maps" :class="j.maps === 'False positive' ? 'vm-fp' : 'vm-ne'">{{ j.maps }}</span>
    </button>
  </div>
</template>

<style scoped>
.vex-chips {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.vex-chip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-sm);
  padding: 7px 10px;
  text-align: left;
  cursor: default;
}
.vex-chip:hover:not(:disabled) {
  border-color: var(--control-hover-line);
}
.vex-chip:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.vex-chip-on {
  border-color: var(--coral);
  background: var(--dd-on-bg);
  box-shadow: inset 0 0 0 1px var(--coral);
}
.vex-chip-label {
  font-size: var(--text-control);
  color: var(--ink);
}
.vex-maps {
  font-size: var(--text-facet-label);
  font-weight: 700;
  font-family: var(--font-mono);
  padding: 2px 6px;
  border-radius: 5px;
  flex: none;
}
.vm-fp {
  background: var(--sev-critical-bg);
  color: var(--sev-critical-fg);
}
.vm-ne {
  background: var(--state-na-bg);
  color: var(--state-na-fg);
}
</style>

<script setup lang="ts">
/**
 * The settings text/number input (prototype `.num-input`/`.text-input` + unit suffix) with the
 * full feedback contract (hover wash shift, focus, invalid) owned once. `unit` renders the
 * mono suffix ("days", "GB"); `num` narrows to the numeric width; `prose` sets text that people
 * write, such as a name or a description, in the UI face. Value stays a string —
 * parsing/validation is the consumer's form logic (contract guards live there).
 */
import { inject } from 'vue'

import { SETTINGS_ROW_LABEL } from '@/components/settings/rowLabel'

withDefaults(
  defineProps<{
    modelValue: string
    num?: boolean
    unit?: string
    invalid?: boolean
    id?: string
    disabled?: boolean
    maxlength?: number
    prose?: boolean
  }>(),
  { num: false, invalid: false, prose: false },
)
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
// inside a SettingsRow the row's title names this input; outside one (a UiField in a dialog)
// the caller binds a <label for> to `id` instead
const row = inject(SETTINGS_ROW_LABEL, null)
</script>

<template>
  <span class="set-input-wrap" :class="{ 'set-input-wrap--block': !num }">
    <input
      :id="id"
      class="set-input"
      :class="{ 'set-input--num': num, 'set-input--invalid': invalid, 'set-input--prose': prose }"
      :value="modelValue"
      :aria-labelledby="row?.labelId"
      :aria-describedby="row?.hintId()"
      :aria-invalid="invalid || undefined"
      :disabled="disabled"
      :maxlength="maxlength"
      :inputmode="num ? 'decimal' : undefined"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <span v-if="unit" class="set-input-unit">{{ unit }}</span>
  </span>
</template>

<style scoped>
.set-input-wrap {
  display: inline-flex;
  align-items: center;
  gap: 9px;
}
/* text inputs fill their row (stacked rows hand them the full track); the inline-flex wrap
   otherwise collapses to the input's intrinsic ~20ch and truncates long values */
.set-input-wrap--block {
  display: flex;
  width: 100%;
}
.set-input-wrap--block .set-input {
  flex: 1;
}
.set-input {
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 8px 11px;
  font-size: var(--text-mono-cell);
  font-family: var(--font-mono);
  color: var(--ink);
  background: var(--card);
  outline: none;
  width: 100%;
  transition:
    border-color var(--dur-quick) var(--ease-out),
    background var(--dur-quick) var(--ease-out);
}
.set-input--num {
  width: 88px;
}
.set-input--prose {
  font-family: var(--font-ui);
  font-size: var(--text-body);
}
.set-input:hover:not(:disabled) {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.set-input:focus {
  border-color: var(--coral);
  background: var(--card);
}
.set-input:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.set-input--invalid {
  border-color: var(--coral-d);
}
.set-input:disabled {
  color: var(--soft);
  background: var(--panel);
  cursor: not-allowed;
}
.set-input-unit {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
</style>

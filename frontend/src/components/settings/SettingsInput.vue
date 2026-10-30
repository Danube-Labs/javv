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
import UiTextBox from '@/components/ui/UiTextBox.vue'

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
    placeholder?: string
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
    <UiTextBox
      :id="id"
      :model-value="modelValue"
      :num="num"
      :prose="prose"
      :invalid="invalid"
      :aria-labelledby="row?.labelId"
      :aria-describedby="row?.hintId()"
      :disabled="disabled"
      :maxlength="maxlength"
      :placeholder="placeholder"
      :inputmode="num ? 'decimal' : undefined"
      @update:model-value="emit('update:modelValue', String($event))"
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
.set-input-wrap--block > input {
  flex: 1;
}
.set-input-unit {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
</style>

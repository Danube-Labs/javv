<script lang="ts">
/**
 * THE date + 24h-time pair (the GlobalTimePicker `time-abs` grammar, extracted for reuse):
 * a native date input (browser calendar popup) beside a strict `HH:mm` field — split on
 * purpose, `datetime-local` renders AM/PM and 24-hour display is a ruling (DESIGN.md §2).
 * Dumb by design: the model is the RAW halves — combining/validating them is the consumer's
 * form logic (so "half-filled" can never silently read as "empty").
 */
export interface DateTimeParts {
  date: string // '' or YYYY-MM-DD (native date input)
  time: string // '' or HH:mm (strict 24h)
}
</script>

<script setup lang="ts">
const props = defineProps<{ modelValue: DateTimeParts; idPrefix?: string; invalid?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: DateTimeParts] }>()

function set(part: 'date' | 'time', value: string) {
  emit('update:modelValue', { ...props.modelValue, [part]: value })
}
</script>

<template>
  <span class="dt-pair">
    <input
      :id="idPrefix ? `${idPrefix}-date` : undefined"
      class="set-input dt-input"
      :class="{ 'set-input--invalid': invalid }"
      type="date"
      aria-label="Date"
      :value="modelValue.date"
      @input="set('date', ($event.target as HTMLInputElement).value)"
    />
    <input
      :id="idPrefix ? `${idPrefix}-time` : undefined"
      class="set-input dt-input dt-hhmm"
      :class="{ 'set-input--invalid': invalid }"
      type="text"
      placeholder="HH:mm"
      maxlength="5"
      aria-label="Time (24h)"
      :value="modelValue.time"
      @input="set('time', ($event.target as HTMLInputElement).value)"
    />
  </span>
</template>

<style scoped>
.dt-pair {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
/* the box look is the shared `.set-input` (base.css); a date box keeps its own width in the pair */
.dt-input {
  width: auto;
}
.dt-hhmm {
  width: 74px;
  text-align: center;
}
</style>

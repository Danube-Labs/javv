<script setup lang="ts" generic="T extends string">
/**
 * A row of buttons that each turn one value on or off, independently (UiSegControl picks ONE
 * value; this picks any number). Same selected look as UiSegControl: the coral tint and inset
 * ring (operator ruling 2026-07-11). The parent owns the list and decides what a toggle does;
 * the group only reports the pressed value. `detail` is an optional mono suffix, e.g. the stored
 * value behind a friendly label.
 */
const props = defineProps<{
  options: readonly { value: T; label: string; detail?: string }[]
  selected: readonly T[]
  label: string
}>()
const emit = defineEmits<{ toggle: [value: T] }>()

const isOn = (value: T) => props.selected.includes(value)
</script>

<template>
  <div class="ui-tg" role="group" :aria-label="label">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="ui-tg-opt"
      :class="{ 'ui-tg-on': isOn(opt.value) }"
      :aria-pressed="isOn(opt.value)"
      @click="emit('toggle', opt.value)"
    >
      <span class="ui-tg-label">{{ opt.label }}</span>
      <span v-if="opt.detail" class="ui-tg-detail mono-cell">{{ opt.detail }}</span>
    </button>
  </div>
</template>

<style scoped>
.ui-tg {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ui-tg-opt {
  display: inline-flex;
  align-items: baseline;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--card);
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: var(--text-control);
  white-space: nowrap;
  padding: 7px 12px;
  cursor: default;
  transition:
    background var(--dur-quick) var(--ease-out),
    border-color var(--dur-quick) var(--ease-out),
    color var(--dur-quick) var(--ease-out);
}
.ui-tg-opt:hover:not(.ui-tg-on) {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.ui-tg-opt:active:not(.ui-tg-on) {
  background: var(--control-active-bg);
}
.ui-tg-opt:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.ui-tg-detail {
  font-size: var(--text-sm);
  color: var(--soft);
}
.ui-tg-on {
  background: var(--dd-on-bg);
  color: var(--coral-text);
  border-color: var(--coral);
  box-shadow: inset 0 0 0 1px var(--coral);
  font-weight: 600;
}
.ui-tg-on .ui-tg-detail {
  color: var(--coral-text);
  font-weight: 400;
}
.ui-tg-on:hover {
  background: var(--control-hover-bg);
}
@media (prefers-reduced-motion: reduce) {
  .ui-tg-opt {
    transition: none;
  }
}
</style>

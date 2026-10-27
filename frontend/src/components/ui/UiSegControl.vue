<script setup lang="ts" generic="T extends string">
/**
 * THE segmented bar (DESIGN.md §2: inner padding + per-option radius so the selected ring is
 * never clipped). ONE selection language — the coral tint (operator ruling 2026-07-11: the old
 * `neutral` tone's white-on-panel selection was unreadable; every seg control selects loudly).
 * Feedback contract lives here, once.
 */
withDefaults(
  defineProps<{
    options: readonly { value: T; label: string; accent?: string }[]
    modelValue: T
    // the group's name for a screen reader: a label above the control does not name a div (issue 1011)
    label: string
  }>(),
  {},
)
const emit = defineEmits<{ 'update:modelValue': [value: T] }>()
</script>

<template>
  <div class="ui-seg" role="group" :aria-label="label">
    <button
      v-for="opt in options"
      :key="opt.value"
      type="button"
      class="ui-seg-opt"
      :class="{ 'ui-seg-on': modelValue === opt.value }"
      :aria-pressed="modelValue === opt.value"
      @click="emit('update:modelValue', opt.value)"
    >
      <i v-if="opt.accent" class="ui-seg-dot" :style="{ background: opt.accent }" aria-hidden="true" />{{ opt.label }}
    </button>
  </div>
</template>

<style scoped>
.ui-seg {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--panel);
}
.ui-seg-opt {
  border: 0;
  border-radius: 5px;
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  white-space: nowrap;
  cursor: default;
  background: var(--card);
  padding: 7px 12px;
  color: var(--ink);
  transition:
    background 120ms ease,
    color 120ms ease;
}
/* identity dot (§8.5 specimen): scanner/category hue as a marker — the coral selection
   language (operator ruling 2026-07-11) stays untouched */
.ui-seg-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 6px;
  vertical-align: 1px;
}
.ui-seg-opt:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.ui-seg-opt:hover:not(.ui-seg-on) {
  background: var(--control-hover-bg);
  color: var(--ink);
}
.ui-seg-opt:active:not(.ui-seg-on) {
  background: var(--control-active-bg);
}
.ui-seg-on {
  background: var(--dd-on-bg);
  color: var(--coral-text);
  box-shadow: inset 0 0 0 1px var(--coral);
  font-weight: 600;
}
@media (prefers-reduced-motion: reduce) {
  .ui-seg-opt {
    transition: none;
  }
}
</style>

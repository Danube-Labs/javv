<script setup lang="ts">
/**
 * THE close button: the "✕" that closes a window, a panel, a popover, a toast or a banner, or
 * clears one value (a chip, a filter). One look everywhere (issue 1140, R2, operator ruling on
 * built pictures): at rest no fill and no line; on hover the kit wash and line, with coral text;
 * a press fill and the focus ring. `dark` is the look on a slate head (a window or the side
 * panel, issue 1049): the colors of the sidebar collapse button. `label` names the button for
 * a screen reader and is its hover text, since the "✕" alone says nothing.
 */
withDefaults(defineProps<{ label: string; dark?: boolean; small?: boolean }>(), {})
</script>

<template>
  <button
    type="button"
    class="ui-close"
    :class="{ 'ui-close--dark': dark, 'ui-close--sm': small }"
    :aria-label="label"
    :title="label"
  >
    ✕
  </button>
</template>

<style scoped>
.ui-close {
  flex: none;
  display: inline-grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--soft);
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  line-height: 1;
  cursor: default;
  transition:
    background var(--dur-quick) var(--ease-out),
    border-color var(--dur-quick) var(--ease-out),
    color var(--dur-quick) var(--ease-out);
}
.ui-close:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
  color: var(--coral-text);
}
.ui-close:active {
  background: var(--control-active-bg);
}
.ui-close:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.ui-close--sm {
  width: 18px;
  height: 18px;
  font-size: var(--text-facet-label);
}
/* on a slate head: the sidebar collapse button's ramp, as the beige wash of the light surfaces
   would flash a pale chip on the band */
.ui-close--dark {
  width: auto;
  height: auto;
  padding: 3px 8px;
  border-color: var(--table-head-line);
  background: var(--side-control-bg);
  color: var(--table-head-fg);
}
.ui-close--dark:hover {
  background: var(--side-control-hover-bg);
  border-color: var(--side-label);
  color: var(--table-head-fg);
}
.ui-close--dark:active {
  background: var(--side-control-active-bg);
}
</style>

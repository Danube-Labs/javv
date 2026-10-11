<script setup lang="ts">
/**
 * THE button. Every variant carries the full interaction contract (DESIGN.md §2:
 * hover wash + border shift, pressed, focus ring, arrow cursor, disabled) internally,
 * so consumers can't ship a button that skips it.
 */
withDefaults(
  defineProps<{
    variant?: 'mini' | 'control' | 'quiet' | 'ghost' | 'primary'
    block?: boolean
  }>(),
  { variant: 'mini' },
)
</script>

<template>
  <button type="button" class="ui-btn" :class="[`ui-btn--${variant}`, { 'ui-btn--block': block }]">
    <slot />
  </button>
</template>

<style scoped>
/* a button label is one line: a wrapped label reads as two controls (issue 652). The space around
   a button gives way instead */
.ui-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  white-space: nowrap;
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-sm);
  font-family: var(--font-ui);
  color: var(--ink);
  cursor: default;
  transition:
    background 120ms ease,
    border-color 120ms ease;
}
.ui-btn:hover:not(:disabled) {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.ui-btn:active:not(:disabled) {
  background: var(--control-active-bg);
}
.ui-btn:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.ui-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}
.ui-btn--mini {
  padding: 4px 9px;
  font-size: var(--text-sm);
}
.ui-btn--control {
  padding: 6px 11px;
  font-size: var(--text-control);
}
.ui-btn--quiet {
  gap: 7px;
  padding: 5px 9px;
  font-size: var(--text-quiet-action);
  font-weight: 600;
  background: var(--panel);
  border-radius: 7px;
}
.ui-btn--ghost,
.ui-btn--primary {
  gap: 7px;
  padding: 8px 14px;
  font-size: var(--text-control);
  font-weight: 600;
}
/* FLAT solid primary (operator 2026-07-17, Nuxt solid grammar): coral fill + inverted text,
   NO gloss — the inset highlight + drop shadow were the "plasticky" read, not the hue.
   (A soft-wash variant was tried and ruled too muted.)
   Press (operator 2026-10-11, variant E on built specimens, issue 817): it sinks 1px and shrinks
   to 97%, and a coral ring shows and fades on release, so a click lands with force. The ring is a
   pseudo-element whose opacity animates: the motion layer moves transform and opacity only. */
.ui-btn--primary {
  position: relative;
  border-color: var(--coral);
  background: var(--coral);
  color: var(--kev-fg);
  transition:
    background 120ms ease,
    border-color 120ms ease,
    transform var(--dur-quick) var(--ease-out);
}
.ui-btn--primary::after {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: inherit;
  box-shadow: 0 0 0 5px var(--coral-drop);
  opacity: 0;
  pointer-events: none;
  transition: opacity calc(var(--dur-panel) * 2) var(--ease-out);
}
.ui-btn--primary:active:not(:disabled) {
  transform: translateY(1px) scale(0.97);
}
.ui-btn--primary:active:not(:disabled)::after {
  opacity: 1;
  transition: none;
}
.ui-btn--primary:hover:not(:disabled) {
  background: var(--coral-dd);
  border-color: var(--coral-dd);
}
.ui-btn--primary:active:not(:disabled) {
  background: var(--coral-dd);
  border-color: var(--coral-dd);
}
.ui-btn--block {
  width: 100%;
}
@media (prefers-reduced-motion: reduce) {
  .ui-btn,
  .ui-btn--primary::after {
    transition: none;
  }
  /* no movement; the darker fill and the ring still say the press landed */
  .ui-btn--primary:active:not(:disabled) {
    transform: none;
  }
}
</style>

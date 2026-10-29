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
    /** the darker border, for a button on a white card where the thin one hardly shows (issue 1004) */
    bordered?: boolean
    /** a control in a screen head: one height for the row, the darker border and a 1px edge (issue 1039) */
    head?: boolean
  }>(),
  { variant: 'mini' },
)
</script>

<template>
  <button
    type="button"
    class="ui-btn"
    :class="[`ui-btn--${variant}`, { 'ui-btn--block': block, 'ui-btn--bordered': bordered, 'ui-btn--head': head }]"
  >
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
/* FLAT solid primary (operator 2026-07-17, Nuxt solid grammar): a solid fill + inverted text,
   NO gloss — the inset highlight + drop shadow were the "plasticky" read, not the hue.
   (A soft-wash variant was tried and ruled too muted.) The fill is slate, not coral (operator
   2026-10-29, issue 1004): coral shares the red-orange of critical, KEV and "down".
   Press (operator 2026-10-11, variant E on built specimens, issue 817): it sinks 1px and shrinks
   to 97%, and a ring shows and fades on release, so a click lands with force. The ring is a
   pseudo-element whose opacity animates: the motion layer moves transform and opacity only. */
.ui-btn--primary {
  position: relative;
  border-color: var(--slate2);
  background: var(--slate2);
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
  box-shadow: 0 0 0 5px var(--slate-drop);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur-panel) var(--ease-out);
}
.ui-btn--primary:active:not(:disabled) {
  transform: translateY(1px) scale(0.97);
}
.ui-btn--primary:active:not(:disabled)::after {
  opacity: 1;
  transition: none;
}
.ui-btn--primary:hover:not(:disabled) {
  background: var(--slate);
  border-color: var(--slate);
}
.ui-btn--primary:active:not(:disabled) {
  background: var(--slate);
  border-color: var(--slate);
}
.ui-btn--block {
  width: 100%;
}
.ui-btn--bordered {
  border-color: var(--control-hover-line);
}
/* a control in a screen head (operator 2026-10-29, option D, issue 1039): every control there is
   the height of the control variant, so the primary and ghost give up their larger padding. The
   head sits on the page paper, so the line is the darker one and a 1px edge with no blur is under it */
.ui-btn--head {
  padding: 6px 11px;
  box-shadow: var(--control-edge);
}
.ui-btn--head:not(.ui-btn--primary) {
  border-color: var(--control-hover-line);
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

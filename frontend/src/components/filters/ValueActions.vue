<script setup lang="ts">
/**
 * Include / exclude actions for ONE facet value (issue 349 §2) — the third part of the M9a
 * filter module, beside `FacetRail` and `FilterBar`. It sits wherever the operator meets a
 * value (a rail row, a grid cell) so "filter to this" and "filter this out" never require
 * opening the Add-filter picker first.
 *
 * Two things here are inherited, not invented:
 * - It renders SPANS, not buttons. Both hosts nest it inside a `<button>` (the rail's
 *   `.facet-row`; the picker's value rows) and a button may not contain a button — the
 *   prototype's own escape hatch for `.fpill-x`. Unlike `.fpill-x` it IS keyboard-operable.
 * - The +/− marks are drawn in CSS, not typed as characters and not added to AppIcon. Text
 *   `+` and `−` carry different vertical metrics in Hanken Grotesk, so a 16px box centred
 *   them by line box and they read visibly off-centre (operator, 2026-07-28); the ported
 *   icon set has no `minus` to reach for either. Two absolutely-centred bars are exact and
 *   cost nothing. The label lives in `aria-label`, so nothing is lost by having no text.
 *
 * Deviation on record (DESIGN.md §8.4): the prototype's filter grammar is include-only, so
 * this affordance has no prototype source. Operator ruling 2026-07-27 chose the ⊕/⊖ pair over
 * a per-value dropdown. Its at-rest-vs-hover reveal is a HOST decision — the visual states
 * live in `base.css` beside `.cell-go` because they key off the host row's `:hover`.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { inText } from '@/filters/typedValues'
import type { FilterMode } from '@/stores/filters'

const props = defineProps<{
  /** Field label, spoken in the aria-label: "Filter out Namespace kube-system". */
  field: string
  /** The value these actions act on. */
  value: string
  /** What the screen calls that value, when it differs from the stored one ("Not affected"). */
  shown?: string
  /** The mode this value is already selected under — that side reads as pressed. */
  active?: FilterMode | null
  /** The host already owns include (the rail row's own click), so show exclude only. */
  excludeOnly?: boolean
}>()

const emit = defineEmits<{ pick: [mode: FilterMode] }>()

/**
 * Snap the bar onto the device-pixel grid (operator ruling 2026-07-28).
 *
 * This grid cannot place it there by itself: at devicePixelRatio 1 the bar inherits a
 * fractional origin from three independent directions — the table card starts at x.5, rows are
 * 37.5px (`--text-mono-cell` 12.5px x 1.5 line-height = 18.75), and column edges are
 * percentages. Everything drawn on it then straddles pixels: measured here, the plus's two 2px
 * strokes each smeared across THREE device pixels, and with different splits per axis
 * (0.75/0.25 down, 0.64/0.36 across) — which is why one stroke read thicker than the other,
 * and why the corners and a 1px divider fringed before them.
 *
 * No CSS can fix it — the offset is unknowable to the stylesheet — so the remainder is measured
 * and handed back as two custom properties the transform consumes, composed WITH the lift
 * rather than fighting it (see `.val-act-reveal` in base.css).
 *
 * Measured on the HOST's `mouseenter`, not the bar's: the bar hangs outside its cell, so the
 * pointer never crosses it on the way in and its own enter event would fire far too late. One
 * listener per instance, on the element that already decides when this is revealed.
 */
const root = ref<HTMLElement | null>(null)
let host: HTMLElement | null = null

function snapToPixelGrid() {
  const el = root.value
  if (!el) return
  const { left, top } = el.getBoundingClientRect()
  // the rect carries whatever transform is applied AT THIS INSTANT — mid-lift that is the snap
  // plus the animation's leftover, not the value last written to `--snap-*`. Subtracting the
  // written value here once baked that leftover into the snap on any re-hover inside the 120ms
  // transition, so the live matrix is read instead (absent in jsdom, hence the guard).
  const t = getComputedStyle(el).transform
  const m =
    t && t !== 'none' && typeof DOMMatrixReadOnly !== 'undefined'
      ? new DOMMatrixReadOnly(t)
      : null
  // rounded because `695.36 % 1` is 0.3600000000000136 in binary floating point, and an
  // unrounded remainder would write that whole tail into the DOM for no sub-pixel benefit
  const frac = (v: number) => -Math.round((((v % 1) + 1) % 1) * 1000) / 1000
  el.style.setProperty('--snap-x', `${frac(left - (m?.m41 ?? 0))}px`)
  el.style.setProperty('--snap-y', `${frac(top - (m?.m42 ?? 0))}px`)
}

onMounted(() => {
  host = root.value?.closest('td, .facet-row') ?? null
  host?.addEventListener('mouseenter', snapToPixelGrid)
})
onBeforeUnmount(() => host?.removeEventListener('mouseenter', snapToPixelGrid))

/** Clicking the side that is already active clears it — the same toggle the row/pill offer. */
const label = (mode: FilterMode) =>
  props.active === mode
    ? `Clear ${mode === 'not' ? 'exclusion of' : 'filter on'} ${inText(props.field)} ${props.shown ?? props.value}`
    : `Filter ${mode === 'not' ? 'out' : 'to'} ${inText(props.field)} ${props.shown ?? props.value}`
</script>

<template>
  <span ref="root" class="val-act" @click.stop>
    <span
      v-if="!excludeOnly"
      class="val-act-btn val-act-is"
      :class="{ 'val-act-on': active === 'is' }"
      role="button"
      tabindex="0"
      :aria-label="label('is')"
      :aria-pressed="active === 'is'"
      :title="label('is')"
      @click="emit('pick', 'is')"
      @keydown.enter.prevent="emit('pick', 'is')"
      @keydown.space.prevent="emit('pick', 'is')"
    />
    <span
      class="val-act-btn val-act-not"
      :class="{ 'val-act-on': active === 'not' }"
      role="button"
      tabindex="0"
      :aria-label="label('not')"
      :aria-pressed="active === 'not'"
      :title="label('not')"
      @click="emit('pick', 'not')"
      @keydown.enter.prevent="emit('pick', 'not')"
      @keydown.space.prevent="emit('pick', 'not')"
    />
  </span>
</template>

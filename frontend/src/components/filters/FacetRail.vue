<script setup lang="ts">
/**
 * Left facet rail (prototype filters.jsx `FacetRail`/`FacetGroup` + `.facet-*` CSS). Renders
 * every listable field from the SAME config the FilterBar uses — one config drives both.
 * Counts come from the server's facets response verbatim; the per-scanner split is shown as a
 * tooltip and never combined client-side (FR-12).
 */
import { computed, ref } from 'vue'

import ValueActions from '@/components/filters/ValueActions.vue'
import { FACET_CAP, facetItems, scannerSplit, type FacetsResponse } from '@/filters/facets'
import { isNegatable, type FilterField, type Selections } from '@/filters/fields.config'
import type { FilterMode, Modes } from '@/stores/filters'

const props = defineProps<{
  fields: readonly FilterField[]
  selections: Selections
  facets: FacetsResponse
  /** the counts read was refused: keep the values, show no count (issue 833, F9) */
  countsUnknown?: boolean
  modes?: Modes
  /** the most values one field takes, where the API caps it (Findings, issue 949) */
  maxValues?: number
}>()

const emit = defineEmits<{
  toggle: [fieldKey: string, value: string]
  pick: [fieldKey: string, value: string, mode: FilterMode]
}>()

/** Exclude is offered only where the backend has an `exclude_*` twin to receive it. */
const negatable = isNegatable

/** The mode this value is selected under, or null when it is not selected at all. */
function activeMode(field: FilterField, value: string): FilterMode | null {
  if (!(props.selections[field.key] ?? []).includes(value)) return null
  return props.modes?.[field.key] ?? 'is'
}

const groups = computed(() =>
  props.fields
    .map((field) => ({ field, items: facetItems(field, props.facets, props.selections[field.key]) }))
    .filter((g): g is { field: FilterField; items: NonNullable<typeof g.items> } => g.items !== null)
    // data-driven sections (no fixed vocabulary) hide until they HAVE buckets — a bare header
    // over nothing reads as broken on a first-run cluster
    .filter((g) => g.items.length > 0 || ('values' in g.field && g.field.values !== undefined)),
)

/**
 * Issue 499: two top-32 data-driven groups (images + tags) made the rail ~2× the viewport,
 * which also defeats its own `position: sticky`. Long groups collapse to the top VISIBLE rows
 * behind a "show all N" expander; expanded, the group scrolls in a bounded viewport instead of
 * growing the page. A SELECTED value never collapses out of sight — an applied filter that the
 * rail hides reads as the rail lying about the query.
 */
const VISIBLE = 8
const expanded = ref(new Set<string>())
type Group = { field: FilterField; items: NonNullable<ReturnType<typeof facetItems>> }
const isOpen = (g: Group) => expanded.value.has(g.field.key)
const hasMore = (g: Group) => g.items.length > VISIBLE
const shown = (g: Group) =>
  !hasMore(g) || isOpen(g)
    ? g.items
    : g.items.filter((it, i) => i < VISIBLE || activeMode(g.field, it.value) !== null)
/** The server stopped at FACET_CAP buckets for this field. It counts the server's buckets, not
 * the items: a 0 of a fixed list (issue 980) or a picked value added at the end is no bucket. */
const capped = (g: Group) =>
  g.field.type === 'terms' &&
  g.field.facetKey !== undefined &&
  (props.facets[g.field.facetKey]?.length ?? 0) >= FACET_CAP
function toggleOpen(g: Group) {
  const next = new Set(expanded.value)
  if (!next.delete(g.field.key)) next.add(g.field.key)
  expanded.value = next
}

const fmt = (n: number) => n.toLocaleString('en-US')
</script>

<template>
  <aside class="facets" aria-label="Filters">
    <slot name="header" />
    <div v-for="g in groups" :key="g.field.key" class="facet">
      <div class="facet-title">{{ g.field.label }}</div>
      <div class="facet-body" :class="{ 'facet-body-open': isOpen(g) }">
      <button
        v-for="it in shown(g)"
        :key="it.value"
        class="facet-row"
        :class="{
          'facet-on': activeMode(g.field, it.value) === 'is',
          'facet-out': activeMode(g.field, it.value) === 'not',
        }"
        :title="it.hint ?? (countsUnknown ? undefined : scannerSplit(it.byScanner))"
        @click="emit('toggle', g.field.key, it.value)"
      >
        <span class="facet-check" />
        <span class="facet-label" :title="it.label">
          <span class="facet-text">
            <slot name="value" :field="g.field" :value="it.value" :label="it.label">{{ it.label }}</slot>
          </span>
        </span>
        <span v-if="it.count !== null" class="facet-count">{{ countsUnknown ? '-' : fmt(it.count) }}</span>
        <!-- the row click already means include, so the action offers the other side only -->
        <ValueActions
          v-if="negatable(g.field)"
          class="val-act-reveal"
          exclude-only
          :field="g.field.label"
          :value="it.value"
          :shown="it.label"
          :active="activeMode(g.field, it.value)"
          @pick="(m) => emit('pick', g.field.key, it.value, m)"
        />
      </button>
      </div>
      <button
        v-if="hasMore(g)"
        class="facet-more"
        :aria-expanded="isOpen(g)"
        @click="toggleOpen(g)"
      >
        {{ isOpen(g) ? 'show fewer' : `show all ${fmt(g.items.length)}` }}
      </button>
      <p v-if="isOpen(g) && capped(g)" class="facet-cap">
        top 32 by count; search reaches the rest
      </p>
      <p
        v-if="maxValues !== undefined && (selections[g.field.key] ?? []).length >= maxValues"
        class="facet-cap"
        role="status"
      >
        A filter takes at most {{ maxValues }} values.
      </p>
    </div>
  </aside>
</template>

<style scoped>
.facets {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 6px;
  box-shadow: var(--shadow);
  position: sticky;
  top: 0;
  width: var(--facet-rail-w);
  flex: none;
}
.facet {
  padding: 8px 4px;
  border-top: 1px solid var(--line2);
}
.facet:first-of-type {
  border-top: 0;
}
/* group headers carry `--ink`, not the `--soft` annotation grey: they title the section
   rather than annotate it, and at 10px mono the soft grey receded into the values it labels
   (operator, 2026-07-28) */
.facet-title {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink);
  padding: 2px 8px 8px;
  font-weight: 700;
}
/* expanded, the group scrolls instead of growing the page: ~10 rows, its own scrollbar,
   and overscroll stays contained so the wheel doesn't fall through to the page mid-list */
.facet-body-open {
  max-height: 320px;
  overflow-y: auto;
  overscroll-behavior: contain;
}
/* the same quiet-action grammar as the FilterBar's clear-all: underlined --soft text,
   coral on hover */
.facet-more {
  border: 0;
  background: transparent;
  color: var(--soft);
  font-size: var(--text-quiet-action);
  text-decoration: underline;
  text-underline-offset: 2px;
  padding: 4px 8px;
  cursor: default;
  text-align: left;
}
.facet-more:hover {
  color: var(--coral-text);
}
.facet-more:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.facet-cap {
  margin: 4px 8px 2px;
  font-size: var(--text-facet-count);
  font-family: var(--font-mono);
  color: var(--soft);
  line-height: 1.4;
}
.facet-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 5px 8px;
  border-radius: 7px;
  text-align: left;
  color: var(--ink);
  font-size: var(--text-control);
  cursor: default;
}
/* the same wash every other control uses. `--panel` was a ~2% step off the card: invisible on
   a good monitor and gone entirely on a TN panel (operator, 2026-07-28). It has to live here
   rather than in base.css's shared hover list — that rule and this component's
   `background: transparent` have equal specificity, so the scoped one, injected later, wins. */
.facet-row:hover {
  background: var(--control-hover-bg);
}
.facet-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.facet-check {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1.5px solid var(--facet-check-line);
  flex: none;
  transition: 0.1s;
}
.facet-on .facet-check {
  background: var(--coral);
  border-color: var(--coral);
  box-shadow: inset 0 0 0 2px var(--card);
}
.facet-on {
  color: var(--ink);
  font-weight: 500;
}
/* an excluded value stays listed and readable (operator ruling 2026-07-27) — struck, not
   hidden, so the operator can see what they ruled out and click it off again. The red is
   `--fpill-not-op`, the same exclusion language the NOT-pill carries. */
.facet-out .facet-label {
  text-decoration: line-through;
  text-decoration-color: var(--fpill-not-op);
  text-decoration-thickness: 1.5px;
  color: var(--soft);
}
.facet-out .facet-check {
  border-color: var(--fpill-not-op);
  background: transparent;
}
/* a long unbroken value truncates on one line (its full text in the title), so the count and
   the action keep their place inside the row: EUI's facet button does the same (issue 652) */
.facet-label {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.facet-text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.facet-count {
  flex: none;
  font-family: var(--font-mono);
  font-size: var(--text-facet-count);
  color: var(--soft);
}
</style>

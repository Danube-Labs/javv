<script setup lang="ts">
/**
 * The checked value rows of the filter bar's edit box: a facet's values with their counts, or
 * the typed values of a text field (issue 949), where a click takes the value out. Same look as
 * the rail's facet rows.
 */
export interface ValueRow {
  value: string
  label: string
  on: boolean
  /** null: the field has no count (a typed value), so the row shows none */
  count: number | null
}

defineProps<{
  rows: readonly ValueRow[]
  /** the counts read was refused: a counted row shows "-" (issue 833, F9) */
  countsUnknown?: boolean
  /** a click removes the value: the row says so on hover */
  removable?: boolean
}>()

const emit = defineEmits<{ toggle: [value: string] }>()
</script>

<template>
  <div class="filter-values">
    <button
      v-for="r in rows"
      :key="r.value"
      class="facet-row"
      :class="{ 'facet-on': r.on }"
      :title="removable ? `Remove ${r.label}` : undefined"
      @click="emit('toggle', r.value)"
    >
      <span class="facet-check" />
      <span class="facet-label">{{ r.label }}</span>
      <span v-if="r.count !== null" class="facet-count">{{
        countsUnknown ? '-' : r.count.toLocaleString('en-US')
      }}</span>
    </button>
  </div>
</template>

<style scoped>
.filter-values {
  max-height: 240px;
  overflow-y: auto;
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
.facet-row:hover {
  background: var(--panel);
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
.facet-label {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.facet-count {
  font-family: var(--font-mono);
  font-size: var(--text-facet-count);
  color: var(--soft);
}
</style>

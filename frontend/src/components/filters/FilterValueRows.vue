<script setup lang="ts">
/**
 * The checked value rows of the filter bar's edit box: a facet's values with their counts, or
 * the typed values of a text field (issue 949), where a click takes the value out. The hover
 * wash and the one-line label follow the rail's facet rows.
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
      :title="removable ? `Remove ${r.label}` : r.label"
      :aria-label="removable ? `Remove ${r.label}` : undefined"
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
/* a long value (a full image repo) stays on one line and truncates; its full text is the title */
.facet-label {
  flex: 1;
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

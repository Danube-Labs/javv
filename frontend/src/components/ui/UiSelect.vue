<script setup lang="ts">
/**
 * THE dropdown: one select that wears the base.css dropdown (`.set-select`, issue 1050) with all
 * its states. The screen writes the options in the slot. `row` is the size of a table row.
 */
withDefaults(defineProps<{ row?: boolean }>(), { row: false })
const model = defineModel<string>({ required: true })
</script>

<template>
  <select v-model="model" class="set-select" :class="{ 'set-select--row': row }">
    <slot />
  </select>
</template>

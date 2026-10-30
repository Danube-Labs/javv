<script setup lang="ts">
/**
 * THE dropdown: one select that wears the base.css dropdown (`.set-select`, issue 1050) with all
 * its states. The screen writes the options in the slot. `row` is the size of a table row, and
 * `small` is the small mono size of the pager.
 */
withDefaults(defineProps<{ row?: boolean; small?: boolean }>(), { row: false, small: false })
const model = defineModel<string>({ required: true })
</script>

<template>
  <select v-model="model" class="set-select" :class="{ 'set-select--row': row, 'set-select--small': small }">
    <slot />
  </select>
</template>

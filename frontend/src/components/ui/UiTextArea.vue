<script setup lang="ts">
/**
 * THE text area: the box of UiTextBox (`.set-input`) on a textarea, which changes only its height
 * (base.css). `prose` sets text that people write in the UI face; `invalid` marks it for the eye
 * and for a screen reader. The screen sets `rows`, `id` and `placeholder` on it directly.
 */
withDefaults(defineProps<{ prose?: boolean; invalid?: boolean }>(), { prose: false, invalid: false })
const model = defineModel<string>({ required: true })
</script>

<template>
  <textarea
    v-model="model"
    class="set-input"
    :class="{ 'set-input--prose': prose, 'set-input--invalid': invalid }"
    :aria-invalid="invalid || undefined"
  />
</template>

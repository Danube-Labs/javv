<script setup lang="ts">
/**
 * THE text box: one input that wears the base.css box (`.set-input`, issue 1050), so every state
 * of the box (hover wash and line, focus, invalid, disabled) is owned once, in the skin. `num`
 * narrows it to a number's width, `prose` sets text that people write in the UI face, and
 * `invalid` marks it for the eye and for a screen reader. It is the only element, so the
 * attributes a screen sets (`id`, `min`, `placeholder`, `aria-*`) land on the input itself.
 */
withDefaults(
  defineProps<{
    type?: 'text' | 'password' | 'date' | 'number'
    num?: boolean
    prose?: boolean
    invalid?: boolean
  }>(),
  { type: 'text', num: false, prose: false, invalid: false },
)
const model = defineModel<string | number>({ required: true })
</script>

<template>
  <input
    v-model="model"
    class="set-input"
    :class="{ 'set-input--num': num, 'set-input--prose': prose, 'set-input--invalid': invalid }"
    :type="type"
    :aria-invalid="invalid || undefined"
  />
</template>

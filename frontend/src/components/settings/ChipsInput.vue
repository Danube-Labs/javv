<script setup lang="ts">
/**
 * The chip-list editor (prototype screens-config.jsx `Chips`): removable chips + an inline
 * input — Enter (or comma) adds the trimmed value, × removes. The consumer owns the list
 * (add/remove emits); dedupe/trim live in the pure scopeForm helpers it pairs with.
 */
import { ref } from 'vue'

defineProps<{ items: string[]; placeholder?: string; inputId?: string }>()
const emit = defineEmits<{ add: [value: string]; remove: [value: string] }>()

const draft = ref('')

function commit() {
  if (draft.value.trim() !== '') {
    emit('add', draft.value)
    draft.value = ''
  }
}
</script>

<template>
  <div class="chips">
    <span v-for="chip in items" :key="chip" class="chip mono-cell">
      {{ chip }}
      <button type="button" class="chip-x" :aria-label="`Remove ${chip}`" @click="emit('remove', chip)">
        ×
      </button>
    </span>
    <!-- eslint-disable-next-line vue/no-restricted-html-elements -- the chip row is the box, and this input inside it has no border of its own -->
    <input
      :id="inputId"
      v-model="draft"
      class="chip-input mono-cell"
      :placeholder="placeholder"
      @keydown.enter.prevent="commit"
      @keydown.,.prevent="commit"
      @blur="commit"
    />
  </div>
</template>

<style scoped>
/* prototype .chips/.chip/.chip-input ported onto tokens */
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  align-items: center;
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  background: var(--card);
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-chip);
  padding: 3px 5px 3px 8px;
}
.chip-x {
  border: 0;
  background: transparent;
  color: var(--soft);
  font-size: var(--text-body);
  line-height: 1;
  padding: 0 3px;
  border-radius: 4px;
  transition: background var(--dur-quick) var(--ease-out);
}
.chip-x:hover {
  background: var(--fpill-x-hover-bg);
  color: var(--ink);
}
.chip-x:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.chip-input {
  flex: 1;
  min-width: 140px;
  border: 0;
  outline: none;
  background: transparent;
  font-size: var(--text-mono-cell);
  color: var(--ink);
  padding: 3px;
}
.chip-input::placeholder {
  color: var(--muted);
}
</style>

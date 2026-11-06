<script setup lang="ts">
/**
 * A value to copy, in the mono box of a token (SCREENS §13.5, §13.9): a token shown one time, or
 * the URL of the MCP endpoint. With `copy`, a Copy button sits beside the box and says "Copied"
 * after a copy. A browser that blocks the clipboard gets a toast, and the text stays selectable.
 */
import { ref } from 'vue'

import UiButton from '@/components/ui/UiButton.vue'
import { copyText } from '@/lib/clipboard'

const props = defineProps<{ value: string; copy?: string }>()

const copied = ref(false)

async function onCopy() {
  copied.value = await copyText(props.value)
}
</script>

<template>
  <div class="copy-value">
    <div class="copy-box mono-cell sm" :class="{ 'copy-box--row': copy }">{{ value }}</div>
    <UiButton v-if="copy" :aria-label="copy" @click="onCopy">{{ copied ? 'Copied ✓' : 'Copy' }}</UiButton>
  </div>
</template>

<style scoped>
.copy-value {
  display: flex;
  align-items: center;
  gap: 10px;
}
.copy-box {
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  word-break: break-all;
  user-select: all;
}
/* beside its Copy button, the box takes the height of a settings value (Cluster's ingest endpoint) */
.copy-box--row {
  padding: 8px 11px;
}
</style>

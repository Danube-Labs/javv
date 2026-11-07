<script setup lang="ts">
/**
 * A value to copy, in the mono box of a token (SCREENS §13.5, §13.9): a token shown one time, or
 * the URL of the MCP endpoint. With `copy`, a Copy button sits beside the box and says "Copied"
 * after a copy. A browser that blocks the clipboard gets a toast, and the text stays selectable.
 * `primary` is for the window whose job is the copy (issue 1127, D3 G): the button is the main
 * action, as tall as the box.
 */
import { ref } from 'vue'

import UiButton from '@/components/ui/UiButton.vue'
import { copyText } from '@/lib/clipboard'

const props = defineProps<{ value: string; copy?: string; primary?: boolean }>()

const copied = ref(false)

async function onCopy() {
  copied.value = await copyText(props.value)
}
</script>

<template>
  <div class="copy-value" :class="{ 'copy-value--primary': primary }">
    <div class="copy-box mono-cell sm" :class="{ 'copy-box--row': copy && !primary }">{{ value }}</div>
    <UiButton v-if="copy" :variant="primary ? 'primary' : undefined" :aria-label="copy" @click="onCopy">
      {{ copied ? 'Copied ✓' : 'Copy' }}
    </UiButton>
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
/* the primary button stands as tall as the box beside it */
.copy-value--primary {
  align-items: stretch;
}
/* beside its Copy button, the box takes the height of a settings value (Cluster's ingest endpoint) */
.copy-box--row {
  padding: 8px 11px;
}
</style>

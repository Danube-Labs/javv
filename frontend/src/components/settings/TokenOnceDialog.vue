<script setup lang="ts">
/**
 * The window that shows a new token one time (SCREENS §13.5 scanner tokens, §13.9 MCP tokens),
 * after a mint, a make or a rotate. The token is never shown again, so the window says so.
 */
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'

import CopyValue from './CopyValue.vue'

defineProps<{ token: string; subtitle: string }>()
const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <ModalShell title="Copy this token now" :subtitle="subtitle" @close="emit('close')">
    <CopyValue :value="token" copy="Copy token" primary />
    <template #actions>
      <UiButton variant="ghost" @click="emit('close')">Done</UiButton>
    </template>
  </ModalShell>
</template>

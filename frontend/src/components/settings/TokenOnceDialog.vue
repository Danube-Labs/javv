<script setup lang="ts">
/**
 * The window that shows a new token one time (SCREENS §13.5 scanner tokens, §13.9 MCP tokens),
 * after a mint, a make or a rotate. The token is never shown again, so the window says so.
 */
import { ref } from 'vue'

import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { copyText } from '@/lib/clipboard'

import CopyValue from './CopyValue.vue'

const props = defineProps<{ token: string; subtitle: string }>()
const emit = defineEmits<{ close: [] }>()

const copied = ref(false)

async function onCopy() {
  copied.value = await copyText(props.token)
}
</script>

<template>
  <ModalShell title="Copy this token now" :subtitle="subtitle" @close="emit('close')">
    <CopyValue :value="token" />
    <template #actions>
      <UiButton variant="primary" @click="onCopy">{{ copied ? 'Copied ✓' : 'Copy token' }}</UiButton>
      <UiButton variant="ghost" @click="emit('close')">Done</UiButton>
    </template>
  </ModalShell>
</template>

<script setup lang="ts">
/**
 * Delete a saved view, after a confirmation (issue 1140, R3). Before, the "×" of the card deleted
 * the view at the first click. The request goes only from the button of this window. The audit
 * log keeps a copy of the deleted view.
 */
import { ref } from 'vue'

import { STORE_READ_ONLY_TYPE } from '@/api/problem'
import { deleteViewApiV1ViewsViewIdDelete } from '@/api/generated'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { viewDeleteFailureCopy } from '@/findings/savedViews'
import { logger } from '@/lib/logger'

const props = defineProps<{ viewId: string; name: string }>()
const emit = defineEmits<{ close: []; deleted: [] }>()

const busy = ref(false)
const error = ref<string | null>(null)

// closing while the request runs would unmount the window and drop its outcome
function close() {
  if (!busy.value) emit('close')
}

async function confirm() {
  busy.value = true
  error.value = null
  const { response, error: problem } = await deleteViewApiV1ViewsViewIdDelete({ path: { view_id: props.viewId } })
  busy.value = false
  const status = response?.status ?? 0
  // 404: deleted already, by somebody else or by an earlier try that answered late
  if (response?.ok || status === 404) {
    emit('deleted')
    return
  }
  logger.warn('view_delete_failed', { view_id: props.viewId, status })
  const readOnly = (problem as { type?: unknown } | undefined)?.type === STORE_READ_ONLY_TYPE
  error.value = viewDeleteFailureCopy(status, readOnly)
}
</script>

<template>
  <ModalShell :title="`Delete ${name}?`" subtitle="You cannot undo this." :width="480" @close="close">
    <p class="dv-copy">
      This deletes the view for each user who can see it. The findings stay. The audit log keeps a copy of the view.
    </p>
    <p v-if="error" class="modal-error" role="alert">{{ error }}</p>
    <template #actions>
      <UiButton variant="ghost" :disabled="busy" @click="close">Cancel</UiButton>
      <UiButton variant="primary" :disabled="busy" @click="confirm">
        {{ busy ? 'Deleting…' : 'Delete view' }}
      </UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.dv-copy {
  margin: 0;
  color: var(--ink);
  line-height: 1.55;
}
</style>

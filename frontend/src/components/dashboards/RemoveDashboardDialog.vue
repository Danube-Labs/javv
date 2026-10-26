<script setup lang="ts">
/**
 * Remove a dashboard, after a confirmation (issue 440, S8c). The delete sends the revision the
 * page read, so a dashboard that somebody changed since is not removed (409, D4). The audit log
 * keeps a copy of the removed dashboard.
 */
import { ref } from 'vue'

import { STORE_READ_ONLY_TYPE } from '@/api/problem'
import { deleteDashboardApiV1DashboardsDashboardIdDelete } from '@/api/generated'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { removeFailureCopy } from '@/dashboards/details'
import { logger } from '@/lib/logger'

const props = defineProps<{ dashboardId: string; name: string; revision: number }>()
const emit = defineEmits<{ close: []; removed: [] }>()

const busy = ref(false)
const error = ref<string | null>(null)

// closing while the request runs would unmount the window and drop its outcome
function close() {
  if (!busy.value) emit('close')
}

async function confirm() {
  busy.value = true
  error.value = null
  const { response, error: problem } = await deleteDashboardApiV1DashboardsDashboardIdDelete({
    path: { dashboard_id: props.dashboardId },
    query: { revision: props.revision },
  })
  busy.value = false
  const status = response?.status ?? 0
  // 404: removed already, by somebody else or by an earlier try that answered late
  if (response?.ok || status === 404) {
    emit('removed')
    return
  }
  logger.warn('dashboard_remove_failed', { status })
  const readOnly = (problem as { type?: unknown } | undefined)?.type === STORE_READ_ONLY_TYPE
  error.value = removeFailureCopy(status, readOnly)
}
</script>

<template>
  <ModalShell :title="`Remove ${name}?`" subtitle="You cannot undo this." :width="480" @close="close">
    <p class="rd-copy">
      This removes the dashboard for each user who can see it. The data of its panels stays. The audit log keeps a
      copy of the dashboard.
    </p>
    <p v-if="error" class="modal-error" role="alert">{{ error }}</p>
    <template #actions>
      <UiButton variant="control" :disabled="busy" @click="close">Cancel</UiButton>
      <UiButton variant="primary" :disabled="busy" @click="confirm">
        {{ busy ? 'Removing…' : 'Remove dashboard' }}
      </UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.rd-copy {
  margin: 0;
  color: var(--ink);
  line-height: 1.55;
}
</style>

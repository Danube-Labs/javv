<script setup lang="ts">
/**
 * The delete confirmation for a retired cluster (issue 765): the admin types the cluster's name,
 * as ruled on the issue, before anything is deleted. Delete removes everything JAVV holds for
 * the cluster except its audit history; snapshots taken before still hold the data. The list of
 * what goes and what stays was ruled on built A/B specimens (2026-10-07).
 */
import { computed, ref } from 'vue'

import { client } from '@/api/client'
import { deleteRetiredClusterApiV1ClustersClusterIdDelete } from '@/api/generated'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import { logger } from '@/lib/logger'

const props = defineProps<{ clusterId: string; clusterName: string }>()
// `changed`: the cluster is no longer what the list showed (brought back, or already deleted)
const emit = defineEmits<{ close: []; deleted: []; changed: [] }>()

const typed = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const matches = computed(() => typed.value.trim() === props.clusterName)

// closing while the request runs would unmount the dialog and drop its outcome
function close() {
  if (!busy.value) emit('close')
}

async function confirm() {
  if (!matches.value) return
  busy.value = true
  error.value = null
  const { response } = await deleteRetiredClusterApiV1ClustersClusterIdDelete({
    client,
    path: { cluster_id: props.clusterId },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('cluster_delete_failed', { status: response?.status })
    const code = response?.status
    if (code === 404) {
      // deleted meanwhile (another admin, or an earlier try that answered late): done
      emit('deleted')
      return
    }
    if (code === 409) emit('changed')
    error.value =
      code === 503
        ? 'JAVV did not finish the delete. Delete the cluster again to finish it.'
        : code === 409
          ? 'Somebody brought the cluster back, so it is not retired now. JAVV deleted nothing.'
          : code === 403
            ? 'Your role cannot delete a cluster. It needs the permission can_manage_retention.'
            : 'JAVV did not delete the cluster. Check the backend connection, then try again.'
    return
  }
  emit('deleted')
}
</script>

<template>
  <ModalShell :title="`Delete ${clusterName}?`" subtitle="You cannot undo this." :width="480" @close="close">
    <p class="confirm-copy">This deletes, for <strong class="mono">{{ clusterName }}</strong>:</p>
    <ul class="gone-list">
      <li>its findings and triage decisions</li>
      <li>its scan history, so a past time no longer shows the cluster</li>
      <li>its scanner tokens, so JAVV refuses the scans of a scanner that still runs</li>
      <li>its settings and scan scope</li>
      <li>its reports and notifications</li>
    </ul>
    <p class="keep-note">JAVV keeps its audit history. The older snapshots still hold its data.</p>
    <UiField label="Type the cluster's name to confirm" for="delete-confirm">
      <SettingsInput id="delete-confirm" v-model="typed" :invalid="typed !== '' && !matches" />
    </UiField>
    <p v-if="error" class="modal-error" role="alert">{{ error }}</p>
    <template #actions>
      <UiButton variant="ghost" :disabled="busy" @click="close">Cancel</UiButton>
      <UiButton variant="primary" :disabled="busy || !matches" @click="confirm">
        {{ busy ? 'Deleting…' : 'Delete cluster' }}
      </UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.gone-list {
  margin: 8px 0 0;
  padding-left: 18px;
  line-height: 1.6;
  color: var(--ink);
}
.keep-note {
  margin: 8px 0 0;
  color: var(--soft);
  font-size: var(--text-sm);
}
.mono {
  font-family: var(--font-mono);
}
</style>

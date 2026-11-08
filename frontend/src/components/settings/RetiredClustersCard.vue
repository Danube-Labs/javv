<script setup lang="ts">
/**
 * Retired clusters (issue 765): a card on the Cluster panel listing every retired cluster, since
 * a retired one leaves the switcher and can no longer be selected. Bring back and Delete live on
 * its rows; Delete needs `can_manage_retention`. Placement ruled on built A/B specimens
 * (2026-10-07). The table is the Settings table skin (the token table's grammar). A cluster whose
 * delete did not finish offers only Delete, with a note saying so (issue 778, ruled B on built
 * specimens 2026-10-08): bringing it back would list a cluster with part of its data gone.
 */
import { computed, onMounted, ref } from 'vue'

import ClusterDeleteDialog from '@/components/settings/ClusterDeleteDialog.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'
import { lastDataAt } from '@/system/freshness'
import { useFleetClusters, type FleetCluster } from '@/views/settings/clusterRetirement'

const fleet = useFleetClusters()
const auth = useAuthStore()
const clusterStore = useClusterStore()
const toast = useToastStore()
const busy = ref(false)
const deleting = ref<FleetCluster | null>(null)

const retired = computed(() => fleet.rows.value.filter((c) => c.retired))
const canDelete = computed(() => auth.hasCapability('can_manage_retention'))

onMounted(() => void fleet.load())
defineExpose({ reload: () => fleet.load() })

async function bringBack(row: FleetCluster) {
  busy.value = true
  const error = await fleet.unretire(row.cluster_id)
  busy.value = false
  if (error) {
    toast.error(error)
  } else {
    // a manual retire revoked its tokens; an automatic one left them working (operator wording,
    // issue 778)
    toast.success(
      row.retirement_mode === 'manual'
        ? `${row.cluster_name} is back on the cluster list. Its tokens were revoked when it was retired: create a new one for its scanners.`
        : `${row.cluster_name} is back on the cluster list`,
    )
    await clusterStore.refresh()
  }
  await fleet.load()
}

// brought back meanwhile: it is on the cluster list again
async function onChanged() {
  await Promise.all([fleet.load(), clusterStore.refresh()])
}

async function onDeleted() {
  const name = deleting.value?.cluster_name
  deleting.value = null
  toast.success(`${name} deleted`)
  await fleet.load()
}
</script>

<template>
  <SettingsCard title="Retired clusters" subtitle="off the cluster list, with their data kept">
    <UiSkeleton v-if="fleet.loading.value" :height="64" radius="sm" label="Loading retired clusters" />
    <p v-else-if="fleet.failed.value" class="load-error" role="alert">
      Retired clusters unavailable. Check the backend connection.
    </p>
    <p v-else-if="retired.length === 0" class="empty-note" role="status">
      No retired clusters. A cluster that sends no scans for its retirement window is retired
      automatically and listed here.
    </p>
    <div v-else class="set-flush">
      <div class="tbl-wrap">
        <table class="tbl tbl-dense tbl-quiet tbl-hover">
          <thead>
            <tr>
              <th>Cluster</th>
              <th class="fit">Last scan</th>
              <th class="fit"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in retired" :key="row.cluster_id">
              <td>
                <span class="name-cell" :title="row.cluster_id">{{ row.cluster_name }}</span>
                <span v-if="row.cluster_name !== row.cluster_id" class="mono-cell sm id-cell">{{
                  row.cluster_id
                }}</span>
                <span v-if="row.delete_started" class="unfinished-cell">{{
                  canDelete
                    ? 'Its delete did not finish. Delete it again.'
                    : 'Its delete did not finish. Someone who can delete clusters must delete it again.'
                }}</span>
              </td>
              <td class="fit mono-cell sm nowrap" :title="row.last_scan_at ?? undefined">
                {{ lastDataAt(row.last_scan_at) }}
              </td>
              <td class="fit">
                <span class="row-actions">
                  <UiButton v-if="!row.delete_started" :disabled="busy" @click="bringBack(row)"
                    >Bring back</UiButton
                  >
                  <UiButton v-if="canDelete" :disabled="busy" @click="deleting = row">Delete…</UiButton>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </SettingsCard>
  <ClusterDeleteDialog
    v-if="deleting"
    :cluster-id="deleting.cluster_id"
    :cluster-name="deleting.cluster_name"
    @close="deleting = null"
    @deleted="onDeleted"
    @changed="onChanged"
  />
</template>

<style scoped>
.name-cell {
  display: block;
  color: var(--ink);
}
.id-cell {
  display: block;
  color: var(--soft);
}
.unfinished-cell {
  display: block;
  font-size: var(--text-sm);
  color: var(--soft);
}
.row-actions {
  display: inline-flex;
  gap: 6px;
}
.load-error,
.empty-note {
  margin: 2px 0;
  color: var(--soft);
  line-height: 1.5;
}
.load-error {
  color: var(--ink);
}
</style>

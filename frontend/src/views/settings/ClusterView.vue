<script setup lang="ts">
/**
 * Cluster panel (§13.8; prototype screens-config.jsx `cluster` section): identity & ingest
 * contract for the SELECTED cluster. `cluster_id` is immutable (the tenant key — never a query
 * key is the NAME's rule, the id routes indices); `cluster_name` is the relabelable display
 * name (D-5 registry, M8c) — the rename is journaled. Ruled prototype deltas (row 9):
 * `schema_version` displays 4 (prototype said 3); the ingest endpoint shows THIS deployment's
 * real path, not a lorem host.
 */
import { computed, ref, watch } from 'vue'

import { renameClusterApiV1ClustersClusterIdNamePut } from '@/api/generated'
import { client } from '@/api/client'
import RetiredClustersCard from '@/components/settings/RetiredClustersCard.vue'
import RetirementWindowCard from '@/components/settings/RetirementWindowCard.vue'
import SaveBar from '@/components/settings/SaveBar.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'

import { useFleetClusters } from './clusterRetirement'

// the envelope contract version this backend accepts (D44 schema v3 → v4 joint stamp, v5 the
// file paths of issue 1077; the ruled §13.8 display value — bump alongside the ingest contract)
const SCHEMA_VERSION = 5

const clusterStore = useClusterStore()
const toast = useToastStore()

const draft = ref('')
watch(
  () => clusterStore.selected?.cluster_name,
  (name) => {
    draft.value = name ?? ''
  },
  { immediate: true },
)

const dirty = computed(
  () => draft.value.trim() !== (clusterStore.selected?.cluster_name ?? '') && draft.value.trim() !== '',
)
const invalid = computed(() => draft.value.trim().length === 0 || draft.value.trim().length > 128)

const busy = ref(false)

async function save() {
  const id = clusterStore.selectedId
  if (!id || invalid.value) return
  busy.value = true
  const { response } = await renameClusterApiV1ClustersClusterIdNamePut({
    client,
    path: { cluster_id: id },
    body: { cluster_name: draft.value.trim() },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('cluster_rename_failed', { status: response?.status })
    toast.error(
      response?.status === 503
        ? 'Somebody else changes the cluster list now. JAVV did not rename the cluster. Try again.'
        : 'JAVV did not rename the cluster. The cluster keeps its current name.',
    )
    return
  }
  toast.success('JAVV renamed the cluster. JAVV uses the name only to show the cluster. It still finds the data by the cluster ID.')
  await clusterStore.refresh()
}

function discard() {
  draft.value = clusterStore.selected?.cluster_name ?? ''
}

const ingestEndpoint = computed(() => `${window.location.origin}/api/v1/ingest/scan`)

// ── retire (issue 765) ──────────────────────────────────────────────────────────────────
const fleet = useFleetClusters()
const retireOpen = ref(false)
const retiredCard = ref<InstanceType<typeof RetiredClustersCard> | null>(null)

async function retire() {
  const id = clusterStore.selectedId
  const name = clusterStore.selected?.cluster_name ?? id
  if (!id) return
  busy.value = true
  const error = await fleet.retire(id)
  busy.value = false
  retireOpen.value = false
  if (error) {
    toast.error(error)
    return
  }
  toast.success(`JAVV retired ${name}. To bring it back, use Retired clusters.`)
  await clusterStore.refresh({ quiet: true })
  await retiredCard.value?.reload()
}
</script>

<template>
  <div class="stack">
    <SettingsCard title="Cluster" subtitle="The identity of the cluster and the address where its scanners send scans.">
      <SettingsRow label="cluster_id" hint="The ID of the cluster. It cannot change. JAVV keeps and finds all data of the cluster by this ID." stack>
        <div class="static-row">
          <span class="static-value mono-sm"><template v-if="clusterStore.selectedId != null">{{ clusterStore.selectedId }}</template><span v-else class="muted-dash">-</span></span>
          <span class="lock-tag">cannot change</span>
        </div>
      </SettingsRow>
      <SettingsRow
        label="cluster_name"
        hint="The name that the app shows. You can change it. JAVV does not use it to find data. The audit log records each rename."
        stack
      >
        <SettingsInput id="cluster-name" v-model="draft" :invalid="invalid && draft !== ''" />
      </SettingsRow>
      <SettingsRow label="Scan endpoint" hint="The scanners send their scans to this address over HTTPS, each with its scanner token." stack>
        <span class="static-value mono-sm">{{ ingestEndpoint }}</span>
      </SettingsRow>
      <SettingsRow label="API version">
        <span class="static-value mono-sm">/v1</span>
      </SettingsRow>
      <SettingsRow label="schema_version" hint="The version of the scan format that this backend accepts.">
        <span class="static-value mono-sm">{{ SCHEMA_VERSION }}</span>
      </SettingsRow>
      <SettingsRow
        label="Retire"
        hint="Retire takes this cluster off the cluster list and revokes its scanner tokens. JAVV keeps its data. You can bring the cluster back, or its first scan with a new scanner token brings it back."
      >
        <UiButton :disabled="busy || clusterStore.selectedId == null" @click="retireOpen = true">
          Retire cluster…
        </UiButton>
      </SettingsRow>
    </SettingsCard>

    <SaveBar :dirty="dirty" :invalid="invalid" :busy="busy" @save="save" @discard="discard" />

    <RetirementWindowCard />

    <RetiredClustersCard ref="retiredCard" />

    <ModalShell
      v-if="retireOpen"
      :title="`Retire ${clusterStore.selected?.cluster_name ?? ''}?`"
      subtitle="You can bring it back later."
      @close="retireOpen = false"
    >
      <p class="confirm-copy">
        The cluster leaves the cluster list, the cluster switcher and All clusters. JAVV revokes its
        scanner tokens and refuses the scans of its scanners. Create new scanner tokens for them. The
        first scan with a new token brings the cluster back. JAVV keeps its findings and its history.
      </p>
      <template #actions>
        <UiButton variant="ghost" @click="retireOpen = false">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy" @click="retire">
          {{ busy ? 'Retiring…' : 'Retire cluster' }}
        </UiButton>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.mono-sm {
  font-family: var(--font-mono);
  font-size: var(--text-mono-cell);
}
.static-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.static-value {
  display: inline-block;
  padding: 8px 11px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  color: var(--ink);
  word-break: break-all;
}
.lock-tag {
  flex: none;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--soft);
  border: 1px solid var(--line);
  padding: 3px 8px;
  border-radius: 5px;
}
</style>

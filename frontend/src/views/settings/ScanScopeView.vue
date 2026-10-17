<script setup lang="ts">
/**
 * Scan scope editor (§13.1; prototype screens-config.jsx `scope` section): what the scanner
 * module discovers and scans for the SELECTED cluster — D43/FR-24, semantics fixed server-side
 * (empty include = all, ignore wins, fail-closed scanner fetch). Reads the D-2 session GET;
 * writes the journaled `PUT /api/v1/scan-scope`. Ruled prototype deltas: the include/ignore
 * "active" toggles are gone — the backend has no such flag, an EMPTY list is the semantics
 * (a toggle would silently drop a configured list); "running workloads only" renders as the
 * read-only D30 fact it is (discovery is always live workloads, never a registry crawl).
 */
import { computed, ref, watch } from 'vue'

import {
  getScanScopeSessionApiV1SettingsScanScopeGet,
  putScanScopeApiV1ScanScopePut,
} from '@/api/generated'
import { client } from '@/api/client'
import ChipsInput from '@/components/settings/ChipsInput.vue'
import SaveBar from '@/components/settings/SaveBar.vue'
import NoClusterState from '@/components/settings/NoClusterState.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiToggleGroup from '@/components/ui/UiToggleGroup.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'

import {
  addChip,
  cloneScope,
  emptyScope,
  removeChip,
  scopeDirty,
  type ScopeDraft,
} from './scopeForm'
import { KIND_BUTTONS, kindNote, splitKinds, toggleKind } from './scopeKinds'

const KIND_OPTIONS = KIND_BUTTONS.map((b) => ({ value: b.kind, label: b.label, detail: b.kind }))

const clusterStore = useClusterStore()
const toast = useToastStore()

const saved = ref<ScopeDraft>(emptyScope())
const draft = ref<ScopeDraft>(emptyScope())
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

watch(
  () => clusterStore.selectedId,
  async (id) => {
    if (!id) return
    loading.value = true
    const { data, response } = await getScanScopeSessionApiV1SettingsScanScopeGet({
      client,
      query: { cluster_id: id },
    })
    loading.value = false
    failed.value = !response?.ok || !data
    if (failed.value) {
      logger.warn('scan_scope_load_failed', { status: response?.status })
      return
    }
    saved.value = (data as { scope: ScopeDraft }).scope
    draft.value = cloneScope(saved.value)
  },
  { immediate: true },
)

const dirty = computed(() => scopeDirty(draft.value, saved.value))
const kinds = computed(() => {
  const { selected, typed } = splitKinds(draft.value.ignore_kinds)
  return {
    selected: [...selected],
    typed,
    notes: typed.flatMap((v) => kindNote(v) ?? []),
  }
})
const bothListsActive = computed(
  () => draft.value.include_namespaces.length > 0 && draft.value.ignore_namespaces.length > 0,
)

async function save() {
  const id = clusterStore.selectedId
  if (!id) return
  busy.value = true
  const { response } = await putScanScopeApiV1ScanScopePut({
    client,
    body: { cluster_id: id, ...draft.value },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('scan_scope_save_failed', { status: response?.status })
    toast.error(
      response?.status === 403
        ? 'Saving needs the can_manage_settings capability.'
        : 'Saving the scan scope failed. The scanner keeps the current one.',
    )
    return
  }
  saved.value = cloneScope(draft.value)
  logger.info('scan_scope_saved', {
    cluster_id: id,
    include_namespaces: draft.value.include_namespaces.length,
    ignore_namespaces: draft.value.ignore_namespaces.length,
    exclude_images: draft.value.exclude_images.length,
    ignore_kinds: draft.value.ignore_kinds,
  })
  toast.success('Scan scope saved. The scanner applies it at its next cycle start')
}

function addIgnoreChip(value: string) {
  // the fail-closed footgun: with globs live, a bare '*' in ignore = scan NOTHING, silently.
  // The server rejects it too — this just keeps the mistake out of the draft.
  if (value.trim() === '*') {
    toast.error("A bare '*' in the ignore list would stop all scanning. Narrow the include list instead.")
    return
  }
  draft.value.ignore_namespaces = addChip(draft.value.ignore_namespaces, value)
}

function discard() {
  draft.value = cloneScope(saved.value)
}
</script>

<template>
  <div>
    <SettingsCard title="Scan scope" subtitle="what the scanner module discovers and scans">
      <NoClusterState v-if="clusterStore.none" />
      <UiSkeleton
        v-else-if="loading"
        :height="280"
        radius="sm"
        label="Loading scan scope"
        class="skel-gap"
      />
      <p v-else-if="failed" class="load-error" role="alert">
        Scan scope unavailable. Check the backend connection.
      </p>

      <template v-else>
        <SettingsRow
          label="Running workloads only"
          hint="Only running images are scanned. Discovery lists running pods through the Kubernetes API and scans each image digest once, however many pods run it."
        >
          <span class="static-fact mono-cell">always on</span>
        </SettingsRow>
        <SettingsRow
          label="Included namespaces"
          hint="Only matching namespaces are scanned: names or glob patterns (kube* covers every kube- namespace). Empty = every namespace."
          stack
        >
          <ChipsInput
            :items="draft.include_namespaces"
            placeholder="add namespace…"
            input-id="scope-include"
            @add="(v) => (draft.include_namespaces = addChip(draft.include_namespaces, v))"
            @remove="(v) => (draft.include_namespaces = removeChip(draft.include_namespaces, v))"
          />
        </SettingsRow>
        <SettingsRow
          label="Ignored namespaces"
          hint="Namespaces the scanner skips: names or globs. Ignore wins over include. A bare * is rejected: it would silently stop all scanning."
          stack
        >
          <ChipsInput
            :items="draft.ignore_namespaces"
            placeholder="add namespace…"
            input-id="scope-ignore"
            @add="addIgnoreChip"
            @remove="(v) => (draft.ignore_namespaces = removeChip(draft.ignore_namespaces, v))"
          />
        </SettingsRow>
        <div v-if="bothListsActive" class="scope-note-banner">
          <AppIcon name="layers" :size="13" />
          Both lists active: the include list is applied first, then ignored namespaces are
          subtracted from it.
        </div>
        <SettingsRow
          label="Excluded image patterns"
          hint="Glob patterns against the full image reference."
          stack
        >
          <ChipsInput
            :items="draft.exclude_images"
            placeholder="*/base-image:*"
            input-id="scope-images"
            @add="(v) => (draft.exclude_images = addChip(draft.exclude_images, v))"
            @remove="(v) => (draft.exclude_images = removeChip(draft.exclude_images, v))"
          />
        </SettingsRow>
        <SettingsRow
          label="Skip workload kinds"
          hint="The scanner does not scan the pods of the workloads that you select."
          stack
        >
          <UiToggleGroup
            :options="KIND_OPTIONS"
            :selected="kinds.selected"
            label="Skip workload kinds"
            @toggle="(k) => (draft.ignore_kinds = toggleKind(draft.ignore_kinds, k))"
          />
        </SettingsRow>
        <SettingsRow
          label="Other owner kinds"
          hint="For an owner kind that is not in the list above, for example Cluster for a CloudNativePG database. Type the kind of the direct owner of the pod, with the same uppercase and lowercase letters as Kubernetes."
          stack
        >
          <ChipsInput
            :items="kinds.typed"
            placeholder="Cluster, VirtualMachineInstance…"
            input-id="scope-kinds"
            @add="(v) => (draft.ignore_kinds = addChip(draft.ignore_kinds, v))"
            @remove="(v) => (draft.ignore_kinds = removeChip(draft.ignore_kinds, v))"
          />
          <div v-for="note in kinds.notes" :key="note" class="scope-note-banner" role="status">
            <AppIcon name="info" :size="13" />
            {{ note }}
          </div>
        </SettingsRow>
      </template>
    </SettingsCard>

    <SaveBar v-if="!loading && !failed" :dirty="dirty" :busy="busy" @save="save" @discard="discard" />
  </div>
</template>

<style scoped>
.static-fact {
  font-size: var(--text-sm);
  color: var(--soft);
  border: 1px solid var(--line);
  border-radius: var(--r-chip);
  padding: 4px 9px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.scope-note-banner {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: var(--text-sweep-strong);
  color: var(--ink);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: 9px;
  padding: 9px 12px;
  line-height: 1.45;
  margin: 12px 0 0;
}
.scope-note-banner svg {
  flex: none;
  color: var(--teal);
}
.load-error {
  margin: 14px 0 8px;
}
.skel-gap {
  margin: 14px 0 8px;
}
</style>

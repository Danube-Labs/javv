<script setup lang="ts">
/**
 * The cluster retirement window (issue 765) on the Cluster panel: retire a silent cluster after
 * N days or never, and how long before that the warning starts. Like the staleness timers, an
 * existing per-cluster override is what gets edited, else the fleet default, and the card says
 * which. The window must clear the scanner-down timer of the doc being edited (the backend checks
 * the same one): the cluster's own for an override, the fleet's for the fleet default.
 */
import { computed, toRef, watch } from 'vue'

import SaveBar from '@/components/settings/SaveBar.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useClusterStore } from '@/stores/cluster'
import { useStalenessStore } from '@/stores/staleness'
import { useToastStore } from '@/stores/toast'
import { useRetirementWindow } from '@/views/settings/retirementForm'

const clusterStore = useClusterStore()
const staleness = useStalenessStore()
const toast = useToastStore()

watch(
  () => clusterStore.selectedId,
  (id) => {
    if (id) void staleness.loadFor(id)
  },
  { immediate: true },
)
void staleness.loadFleet()
// null until the right read lands (or when it failed): the form then leaves the check to the
// backend's 422, whose message the save shows
const scannerDown = computed<number | null>(() => {
  if (!form.override.value) return staleness.fleet?.scanner_down_days ?? null
  const id = clusterStore.selectedId
  return id !== null && staleness.effectiveFor === id ? (staleness.effective?.scanner_down_days ?? null) : null
})
const form = useRetirementWindow(toRef(clusterStore, 'selectedId'), scannerDown)
const scannerDownNote = computed(() =>
  scannerDown.value === null
    ? 'Must be longer than the scanner-down timer.'
    : `Must be longer than the scanner-down timer (${scannerDown.value} days).`,
)

const MODES = [
  { value: 'after', label: 'After a silence' },
  { value: 'never', label: 'Never' },
] as const

async function save() {
  const error = await form.save()
  if (error) {
    toast.error(error)
    return
  }
  toast.success('Retirement window saved. The next retirement sweep applies it')
  // the countdown banner reads the schedule off the cluster list
  await clusterStore.refresh()
}
</script>

<template>
  <SettingsCard
    title="Cluster retirement"
    subtitle="a cluster that stops sending scans leaves the cluster list, with its data kept"
  >
    <UiSkeleton v-if="form.loading.value" :height="96" radius="sm" label="Loading retirement" />
    <p v-else-if="form.failed.value" class="load-error" role="alert">
      Retirement window unavailable. Check the backend connection.
    </p>
    <template v-else>
      <SettingsRow
        label="Retire a silent cluster"
        :hint="`A cluster that sends no scans this long leaves the cluster list. Its data is kept, and a new scan brings it back. ${scannerDownNote}`"
      >
        <div class="retire-ctl">
          <UiSegControl v-model="form.mode.value" :options="MODES" label="Retire a silent cluster" />
          <SettingsInput
            v-if="form.mode.value === 'after'"
            id="retire-after"
            v-model="form.draftAfter.value"
            num
            unit="days"
            :invalid="form.problem.value?.field === 'after'"
          />
        </div>
      </SettingsRow>
      <SettingsRow
        label="Warn before"
        hint="How long before retirement the countdown banner shows."
      >
        <SettingsInput
          id="retire-warn"
          v-model="form.draftWarn.value"
          num
          unit="days"
          :invalid="form.problem.value?.field === 'warn'"
        />
      </SettingsRow>
      <p v-if="form.problem.value" class="retire-problem" role="alert">{{ form.problem.value.message }}</p>
      <p class="scope-src">
        {{
          form.override.value
            ? 'Editing THIS cluster\'s override. The fleet default stays untouched.'
            : clusterStore.selectedId
              ? 'Editing the fleet-wide default (no override exists for this cluster).'
              : 'Editing the fleet-wide default.'
        }}
      </p>
    </template>
  </SettingsCard>
  <SaveBar
    v-if="!form.loading.value && !form.failed.value"
    :dirty="form.dirty.value"
    :invalid="form.problem.value !== null"
    :busy="form.busy.value"
    @save="save"
    @discard="form.discard"
  />
</template>

<style scoped>
.retire-ctl {
  display: flex;
  align-items: center;
  gap: 10px;
}
.retire-problem {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
.scope-src {
  margin: 10px 0 2px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.load-error {
  margin: 14px 0 8px;
}
</style>

<script setup lang="ts">
/**
 * The name, description, sharing and opening scanner of a dashboard (issue 440, S8c; SCREENS
 * §20). In edit mode, Apply puts the details in the draft and the save bar saves them with the
 * panels, as the panel settings do. For a new dashboard, Create sends them to the server: the
 * page owns that request, and shows its error here.
 *
 * The roles come from the server (ruling of 2026-10-26: no role name in the client), with each
 * role, admin too. A role of the dashboard that the list does not have still shows, so a saved
 * choice is never lost without a word.
 */
import { computed, onMounted, ref } from 'vue'

import { listSharingRolesApiV1DashboardsRolesGet } from '@/api/generated'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import UiToggleGroup from '@/components/ui/UiToggleGroup.vue'
import {
  DESCRIPTION_MAX,
  NAME_MAX,
  SHARING_OPTS,
  detailsOf,
  detailsProblem,
  normalized,
  roleOptions,
  toggled,
  type DashboardDetails,
} from '@/dashboards/details'
import { readFailureCopy } from '@/findings/failureCopy'
import { logger } from '@/lib/logger'
import { SCANNER_SWITCH_OPTS } from '@/lib/scannerLens'

const props = defineProps<{
  details: DashboardDetails
  mode: 'create' | 'edit'
  busy?: boolean
  error?: string | null
}>()
const emit = defineEmits<{ close: []; apply: [details: DashboardDetails] }>()

const form = ref<DashboardDetails>(detailsOf(props.details))
const problem = computed(() => detailsProblem(form.value))

const listed = ref<string[]>([])
const rolesLoaded = ref(false)
const rolesFailed = ref<number | null>(null)
const options = computed(() => roleOptions(listed.value, form.value.roles))

onMounted(async () => {
  const { response, data } = await listSharingRolesApiV1DashboardsRolesGet()
  if (response?.ok && data) listed.value = data.roles ?? []
  else {
    logger.warn('dashboard_roles_failed', { status: response?.status ?? 0 })
    rolesFailed.value = response?.status ?? 0
  }
  rolesLoaded.value = true
})

function close() {
  if (!props.busy) emit('close')
}
function apply() {
  if (problem.value === null && !props.busy) emit('apply', normalized(form.value))
}
</script>

<template>
  <ModalShell
    :title="mode === 'create' ? 'New dashboard' : 'Name and sharing'"
    subtitle="Its name, who can see it and the scanner it opens on. The owner and an admin can change it."
    :width="560"
    @close="close"
  >
    <div>
      <UiField label="Name" for="dash-name" first>
        <SettingsInput id="dash-name" v-model="form.name" prose :maxlength="NAME_MAX" :invalid="!form.name.trim()" />
      </UiField>
      <UiField label="Description" hint="optional" for="dash-description">
        <SettingsInput id="dash-description" v-model="form.description" prose :maxlength="DESCRIPTION_MAX" />
      </UiField>
      <UiField label="Who can see it">
        <UiSegControl v-model="form.sharing" :options="SHARING_OPTS" />
      </UiField>
      <UiField v-if="form.sharing === 'roles'" label="Roles">
        <UiSkeleton v-if="!rolesLoaded" :height="36" label="Loading the roles" />
        <template v-else>
          <p v-if="rolesFailed !== null" class="load-error" role="alert">
            {{ readFailureCopy(rolesFailed, 'The list of roles did not load. Close this window and try again.') }}
          </p>
          <UiToggleGroup
            v-if="options.length"
            label="Roles that can see the dashboard"
            :options="options"
            :selected="form.roles"
            @toggle="form.roles = toggled(form.roles, $event)"
          />
        </template>
        <p class="dd-help">An admin can see each dashboard.</p>
      </UiField>
      <UiField label="Opens on" hint="the scanner switch when the page opens">
        <UiSegControl v-model="form.scanner" :options="SCANNER_SWITCH_OPTS" />
      </UiField>
      <p v-if="problem" id="dd-problem" class="dd-help">{{ problem }}</p>
      <p v-if="error" class="modal-error" role="alert">{{ error }}</p>
    </div>
    <template #actions>
      <UiButton variant="control" :disabled="busy" @click="close">Cancel</UiButton>
      <UiButton
        variant="primary"
        :disabled="problem !== null || busy"
        :aria-describedby="problem ? 'dd-problem' : undefined"
        @click="apply"
      >
        {{ mode === 'create' ? (busy ? 'Creating…' : 'Create') : 'Apply' }}
      </UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.dd-help {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
</style>

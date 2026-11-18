<script setup lang="ts">
/**
 * SLA policy panel (§13.3; prototype screens-config.jsx `sla` section): remediation days per
 * severity + the KEV override — GET open to any session, PUT gated `can_manage_settings` and
 * journaled with the full old/new policy (D17). Two spec-truths replace prototype copy: edits
 * apply IMMEDIATELY (the policy is read live per request — deadlines recompute, nothing is
 * "not rewritten"), and negligible/unknown carry NO SLA by ruling (tests/test_sla.py).
 * KEV is a DAYS window with no on/off toggle (D46 `kev_days`), not the prototype's hours+switch.
 */
import { computed, ref } from 'vue'

import { getSlaApiV1SettingsSlaGet, putSlaApiV1SettingsSlaPut } from '@/api/generated'
import type { SlaPolicy } from '@/api/generated'
import { client } from '@/api/client'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import SaveBar from '@/components/settings/SaveBar.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import SevChip from '@/components/chips/SevChip.vue'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

import {
  draftFromPolicy,
  isDirty,
  parseWindow,
  policyFromDraft,
  SLA_SEVERITY_ROWS,
  type SlaDraft,
} from './slaForm'

const toast = useToastStore()

const saved = ref<SlaPolicy | null>(null)
const draft = ref<SlaDraft | null>(null)
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

async function load() {
  loading.value = true
  const { data, response } = await getSlaApiV1SettingsSlaGet({ client })
  loading.value = false
  failed.value = !response?.ok || !data
  if (failed.value) {
    logger.warn('sla_policy_load_failed', { status: response?.status })
    return
  }
  saved.value = (data as { sla: SlaPolicy }).sla
  draft.value = draftFromPolicy(saved.value)
}
void load()

const dirty = computed(() =>
  draft.value !== null && saved.value !== null ? isDirty(draft.value, saved.value) : false,
)
const invalid = computed(() => draft.value !== null && policyFromDraft(draft.value) === null)

const SAVE_FAILURE: Record<number, string> = {
  403: 'Your role cannot change the settings. It needs the permission can_manage_settings.',
  422: 'JAVV refused the policy. Each window must be a number of days more than 0.',
}

async function save() {
  if (draft.value === null) return
  const body = policyFromDraft(draft.value)
  if (body === null) return
  busy.value = true
  const { response } = await putSlaApiV1SettingsSlaPut({ client, body })
  busy.value = false
  if (!response?.ok) {
    logger.warn('sla_policy_save_failed', { status: response?.status })
    toast.error(
      SAVE_FAILURE[response?.status ?? 0] ?? 'JAVV did not save the SLA policy. Nothing changed.',
    )
    return
  }
  saved.value = body
  draft.value = draftFromPolicy(body)
  toast.success('JAVV saved the SLA policy. The deadlines change at once.')
}

function discard() {
  if (saved.value !== null) draft.value = draftFromPolicy(saved.value)
}
</script>

<template>
  <div>
    <SettingsCard
      title="SLA policy"
      subtitle="The deadline for each severity. It sets the SLA column and the overdue marks."
    >
      <UiSkeleton
        v-if="loading"
        :height="280"
        radius="sm"
        label="Loading SLA policy"
        class="skel-gap"
      />

      <p v-else-if="failed" class="load-error" role="alert">
        JAVV cannot show the SLA policy. Check the backend connection.
      </p>

      <template v-else-if="draft">
        <SettingsRow
          v-for="row in SLA_SEVERITY_ROWS"
          :key="row.key"
          :hint="
            row.key === 'critical_days'
              ? 'The clock starts when a scan first finds the finding.'
              : undefined
          "
        >
          <template #label><SevChip :level="row.severity" /></template>
          <SettingsInput
            v-model="draft[row.key]"
            num
            unit="days"
            :invalid="parseWindow(draft[row.key]) === null"
            :id="`sla-${row.key}`"
          />
        </SettingsRow>
        <SettingsRow
          label="KEV override"
          hint="Known-exploited findings get this shorter window, not the table above. You can use a fraction: 0.5 is 12 hours."
        >
          <SettingsInput
            v-model="draft.kev_days"
            num
            unit="days"
            :invalid="parseWindow(draft.kev_days) === null"
            id="sla-kev_days"
          />
        </SettingsRow>
        <div class="sla-note">
          <AppIcon name="info" :size="13" />
          <span>
            A change applies at once. JAVV calculates each deadline from this policy, also for the
            findings that exist now. The severities <b>negligible</b> and <b>unknown</b> have no SLA.
          </span>
        </div>
      </template>
    </SettingsCard>

    <SaveBar
      v-if="!loading && !failed"
      :dirty="dirty"
      :invalid="invalid"
      :busy="busy"
      @save="save"
      @discard="discard"
    />
  </div>
</template>

<style scoped>
/* prototype .ignore-best note grammar (quiet inset banner), ink prose per DESIGN.md §2 */
.sla-note {
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
  margin-top: 14px;
}
.sla-note svg {
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

<script setup lang="ts">
/**
 * Edit a standing risk-acceptance (M9d slice 4) — PATCH /decisions/{id}, the server's ATOMIC
 * revoke+new (D40: one effective_at + operation_id; the old row strikes through, a new
 * decision_id appears). Only the human-judgment fields are editable here — justification and
 * expiry; scope/scanner re-targeting is a different decision, made from the finding.
 */
import { computed, ref } from 'vue'

import { editApiV1DecisionsDecisionIdPatch } from '@/api/generated'
import { EXPIRY_PASSED_TYPE } from '@/api/problem'
import {
  EXPIRY_REFUSED,
  expiryStatus,
  firstExpiryDate,
  type ApprovalRow,
} from '@/approvals/viewModel'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import { logger } from '@/lib/logger'

const props = defineProps<{ decision: ApprovalRow }>()
const emit = defineEmits<{ close: []; edited: [] }>()

const currentDay = props.decision.expiry ? props.decision.expiry.slice(0, 10) : ''
const justification = ref(props.decision.justification)
const expiry = ref(currentDay)
const submitting = ref(false)
const error = ref<string | null>(null)

// an edit keeps the current expiry unless it sets one, so a decision whose expiry has passed
// needs a new date: the server refuses to make a dead decision (issue 984)
const now = Date.now()
const minExpiry = firstExpiryDate(now)
const currentExpired = expiryStatus(props.decision.expiry, now) === 'expired'
const expiryOk = computed(() =>
  expiry.value === '' || expiry.value === currentDay ? !currentExpired : expiry.value >= minExpiry,
)

const dirty = computed(
  () => justification.value.trim() !== props.decision.justification || expiry.value !== currentDay,
)
const valid = computed(() => justification.value.trim().length > 0 && dirty.value && expiryOk.value)

async function submit() {
  if (!valid.value || submitting.value) return
  submitting.value = true
  error.value = null
  const changes: Record<string, string> = {}
  if (justification.value.trim() !== props.decision.justification)
    changes.justification = justification.value.trim()
  if (expiry.value && expiry.value !== currentDay) changes.expiry = expiry.value
  const response = await editApiV1DecisionsDecisionIdPatch({
    path: { decision_id: props.decision.decision_id },
    body: changes,
  })
  submitting.value = false
  if (response.response?.ok) {
    logger.info('decision_edited', { decision_id: props.decision.decision_id })
    emit('edited')
    emit('close')
  } else {
    error.value =
      response.response?.status === 409
        ? 'This decision was already revoked. Refresh the queue.'
        : (response.error as { type?: unknown } | undefined)?.type === EXPIRY_PASSED_TYPE
          ? EXPIRY_REFUSED
          : 'Could not apply the edit. Check the backend connection.'
    logger.warn('decision_edit_failed', { status: response.response?.status })
  }
}
</script>

<template>
  <ModalShell
    title="Edit risk-acceptance"
    :subtitle="decision.cve_id"
    :width="520"
    @close="emit('close')"
  >
    <p class="ed-note">
      An edit is <b>revoke + new</b> (decisions are immutable): the current decision is
      revoked and a new one takes effect atomically, keeping the audit trail causal.
    </p>
    <UiField label="Justification" for="ed-just">
      <textarea id="ed-just" v-model="justification" class="fld ed-just" rows="4" />
    </UiField>
    <UiField label="Expiry" :hint="expiryOk ? 'empty keeps the current expiry' : EXPIRY_REFUSED" for="ed-expiry">
      <input id="ed-expiry" v-model="expiry" class="fld" type="date" :min="minExpiry" :aria-invalid="!expiryOk" />
    </UiField>
    <p v-if="error" class="modal-error" role="alert">{{ error }}</p>
    <template #actions>
      <UiButton variant="quiet" @click="emit('close')">Cancel</UiButton>
      <UiButton :disabled="!valid || submitting" @click="submit">
        {{ submitting ? 'Saving…' : 'Revoke + re-issue' }}
      </UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.ed-note {
  margin: 0 0 12px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.ed-just {
  resize: vertical;
}
</style>

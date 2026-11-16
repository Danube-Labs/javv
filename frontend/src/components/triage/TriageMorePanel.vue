<script setup lang="ts">
/**
 * What "Note and more…" opens next to the Triage cell (issue 1205, G2 with the quick buttons):
 * the lines that explain the state, the reason for Not affected, the note, the risk acceptance
 * and Save. It holds no draft of its own: the cell owns the one draft, so the two Save buttons
 * save the same change. The Undo line and the save error stay in the cell (operator, 2026-11-16).
 */
import { computed } from 'vue'

import VexJustificationPicker from '@/components/triage/VexJustificationPicker.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiTextArea from '@/components/ui/UiTextArea.vue'
import type { FindingRow } from '@/stores/findings'

const props = defineProps<{
  finding: FindingRow
  canTriage: boolean
  canAcceptFinal: boolean
  historical: boolean
  /** no can_triage, or the page shows history */
  locked: boolean
  /** the state of a risk-accepted finding, for a role without can_accept_audit_final */
  acceptLocked: boolean
  /** the state that the draft shows: the picked one, else the finding's */
  shownState: string
  notes: string
  vexJustification: string | null
  draftError: string | null
  canSave: boolean
  saving: boolean
}>()
const emit = defineEmits<{
  'update:notes': [value: string]
  'update:vexJustification': [value: string | null]
  save: []
  riskAccept: []
}>()

const noteText = computed({
  get: () => props.notes,
  set: (v: string) => emit('update:notes', v),
})
</script>

<template>
  <div class="triage-more">
    <div v-if="historical" class="triage-locked">
      <AppIcon name="clock" :size="13" />
      This page shows the state at a past time. You cannot change it here. To change the state, select Back to now.
    </div>
    <div v-else-if="!canTriage" class="triage-locked">
      <AppIcon name="key" :size="13" />
      <span>
        Your role does not allow triage (<b>can_triage</b>). To change the state, ask a triager, a security
        lead or an admin.
      </span>
    </div>
    <p v-if="acceptLocked && !locked" class="triage-locked triage-accept-locked">
      <AppIcon name="key" :size="13" />
      <span>
        To change a risk acceptance, your role must allow risk acceptance (<b>can_accept_audit_final</b>).
        You can still assign this finding and add a note.
      </span>
    </p>

    <div v-if="finding.state === 'risk_accepted'" class="ro-state ro-risk">
      <AppIcon name="shield" :size="13" />
      <div>
        <b>Set by a decision</b>
        <span>
          A decision on this vulnerability sets this state. The decision has a scope, an approver and an expiry date. To
          change this state, use Decisions on this vulnerability.
        </span>
      </div>
    </div>
    <div v-if="finding.state === 'stale'" class="ro-state ro-stale">
      <AppIcon name="clock" :size="13" />
      <div>
        <b>Set by JAVV</b>
        <span>No recent scan confirms this finding. The data can be old. If you set a state, it replaces Stale.</span>
      </div>
    </div>

    <UiField v-if="shownState === 'not_affected'" label="Reason (required)" first>
      <VexJustificationPicker
        :selected="vexJustification"
        :disabled="locked"
        @select="(id) => emit('update:vexJustification', id)"
      />
    </UiField>

    <UiField label="Note" for="triage-notes" :first="shownState !== 'not_affected'">
      <UiTextArea
        id="triage-notes"
        v-model="noteText"
        prose
        rows="2"
        placeholder="Add a note for Activity…"
        :disabled="locked"
      />
    </UiField>

    <p v-if="draftError" class="draft-error" role="alert">{{ draftError }}</p>

    <UiButton v-if="canAcceptFinal" variant="ghost" block class="btn-gap" :disabled="historical" @click="emit('riskAccept')">
      <AppIcon name="shield" :size="14" />Accept the risk of this vulnerability…
    </UiButton>
    <UiButton variant="primary" block class="btn-gap" :disabled="!canSave" @click="emit('save')">
      {{ saving ? 'Saving…' : 'Save' }}
    </UiButton>
    <p class="triage-foot">
      <AppIcon name="clock" :size="11" />JAVV records who saved each change and when. Activity lists the changes.
    </p>
  </div>
</template>

<style scoped>
.triage-locked {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--hist-bg);
  border: 1px solid var(--hist-line);
  border-radius: var(--r-sm);
  padding: 8px 10px;
  margin-bottom: 12px;
  line-height: 1.45;
}
.triage-locked svg {
  flex: none;
  color: var(--hist-fg);
}
.ro-state {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  border-radius: var(--r-sm);
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: var(--text-sm);
  line-height: 1.45;
  color: var(--ink);
}
.ro-state svg {
  flex: none;
  margin-top: 2px;
}
.ro-state b {
  display: block;
  font-size: var(--text-control);
  margin-bottom: 2px;
}
.ro-state span {
  color: var(--soft);
}
.ro-risk {
  background: var(--hist-bg);
  border: 1px solid var(--hist-line);
}
.ro-risk svg {
  color: var(--hist-fg);
}
.ro-stale {
  background: var(--state-stale-bg);
  border: 1px solid var(--state-stale-line);
}
.ro-stale svg {
  color: var(--state-stale-fg);
}
.draft-error {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
.btn-gap {
  margin-top: 8px;
}
.triage-foot {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-facet-label);
  color: var(--soft);
  margin: 10px 0 0;
  line-height: 1.4;
}
.triage-foot svg {
  flex: none;
}
</style>

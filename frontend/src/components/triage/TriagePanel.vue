<script setup lang="ts">
/**
 * The triage aside (prototype `.triage` on tokens) — FR-7 two-field VEX. Read-only when the
 * user lacks can_triage, and when viewing history (T<now: reconstructed state is not editable).
 * Without can_accept_audit_final the state of a risk-accepted finding is locked too (issue 892);
 * the note and the assignee stay open.
 * risk_accepted and stale render explainer blocks instead of buttons; the presence explainer
 * (fixed vs stale) is kept verbatim from the prototype. Save emits the validated PATCH body —
 * the parent owns the network call and conflict surfacing. After a saved state change the parent
 * passes `undo`, and the panel offers the way back (issue 681).
 */
import { computed, ref, watch } from 'vue'

import StateTag from '@/components/chips/StateTag.vue'
import TriageStateControl from '@/components/triage/TriageStateControl.vue'
import VexJustificationPicker from '@/components/triage/VexJustificationPicker.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import { stateLabel } from '@/findings/stateLabels'
import { buildTriagePatch, holdsRiskAccept, type TriagePatchBody } from '@/findings/triageRules'
import type { FindingRow } from '@/stores/findings'

const props = defineProps<{
  finding: FindingRow
  canTriage: boolean
  canAcceptFinal: boolean
  historical: boolean
  saving: boolean
  error: string | null
  currentUser: string | null
  /** The last saved state change on this finding, while it can still be undone. */
  undo?: { from: string; to: string } | null
}>()
const emit = defineEmits<{ save: [body: TriagePatchBody]; riskAccept: []; undo: [] }>()

const target = ref<string | null>(null)
const vexJustification = ref<string | null>(null)
const notes = ref('')
const assignee = ref<string | null>(null)

watch(
  () => props.finding.finding_key,
  () => {
    target.value = null
    vexJustification.value = null
    notes.value = ''
    assignee.value = null
  },
)

const locked = computed(() => !props.canTriage || props.historical)
const acceptLocked = computed(() => !props.canAcceptFinal && holdsRiskAccept(props.finding))
const shownState = computed(() => target.value ?? props.finding.state)
const draft = computed(() =>
  buildTriagePatch({
    currentState: props.finding.state,
    targetState: target.value,
    vexJustification: vexJustification.value,
    notes: notes.value,
    assignee: assignee.value,
  }),
)

function pickState(s: string) {
  if (locked.value || acceptLocked.value) return
  target.value = s
  if (s !== 'not_affected') vexJustification.value = null
}
function save() {
  if (draft.value.body) emit('save', draft.value.body)
}
function undoLast() {
  // the picked target is the state being undone: left in place it would read as a pending change
  target.value = null
  vexJustification.value = null
  emit('undo')
}
</script>

<template>
  <aside class="triage">
    <div class="triage-head">
      <AppIcon name="shield" :size="16" /><span>Triage</span>
      <StateTag class="head-state" :state="finding.state" />
    </div>
    <div class="triage-body">
      <div v-if="historical" class="triage-locked">
        <AppIcon name="clock" :size="13" />
        Viewing history: reconstructed state is read-only. Return to now to triage.
      </div>
      <div v-else-if="!canTriage" class="triage-locked">
        <AppIcon name="key" :size="13" />
        Read-only: you don't hold <b>can_triage</b>. Ask an Operator or Security Lead.
      </div>

      <p v-if="undo && !locked" class="triage-undo" role="status">
        <span>
          Changed from <b>{{ stateLabel(undo.from) }}</b> to <b>{{ stateLabel(undo.to) }}</b> just now.
        </span>
        <UiButton :disabled="saving" @click="undoLast">Undo</UiButton>
      </p>

      <UiField label="Assigned to" first>
        <div class="assignee-row">
          <!-- nobody owning an open finding is a state worth noticing, not quiet prose -->
          <span v-if="assignee ?? finding.assignee" class="assignee-val">{{ assignee ?? finding.assignee }}</span>
          <span v-else class="assignee-none">unassigned</span>
          <UiButton
            v-if="currentUser"
            :disabled="locked || (assignee ?? finding.assignee) === currentUser"
            @click="assignee = currentUser"
          >
            Assign to me
          </UiButton>
        </div>
      </UiField>

      <UiField label="State">
        <TriageStateControl
          :current="finding.state"
          :target="target"
          :disabled="locked || acceptLocked"
          @select="pickState"
        />
      </UiField>
      <p v-if="acceptLocked && !locked" class="triage-locked triage-accept-locked">
        <AppIcon name="key" :size="13" />
        <span>
          A risk-accept is changed by a Security Lead (<b>can_accept_audit_final</b>). You can still
          assign this finding and add a note.
        </span>
      </p>

      <div v-if="shownState === 'not_affected'" class="vex-block">
        <UiField label="Reason (required)">
          <VexJustificationPicker
            :selected="vexJustification"
            :disabled="locked"
            @select="(id) => (vexJustification = id)"
          />
        </UiField>
      </div>

      <div v-if="finding.state === 'risk_accepted'" class="ro-state ro-risk">
        <AppIcon name="shield" :size="13" />
        <div>
          <b>Set by a scoped decision</b>
          <span>Risk-accept isn't toggled here: it comes from a decision (scope + approver + expiry). Manage it below.</span>
        </div>
      </div>
      <div v-if="finding.state === 'stale'" class="ro-state ro-stale">
        <AppIcon name="clock" :size="13" />
        <div>
          <b>System-set · scanner went silent</b>
          <span>The scanner stopped reporting this finding; data may be old. A human state change overrides it.</span>
        </div>
      </div>

      <p class="presence-note">
        <i class="pn-dot pn-fixed" /><b>Fixed</b>&nbsp;· gone from the latest scan, drops off "now"
        &nbsp;&nbsp;<i class="pn-dot pn-stale" /><b>Stale</b>&nbsp;· scanner silent, flagged
      </p>

      <UiField label="Note" for="triage-notes">
        <textarea
          id="triage-notes"
          v-model="notes"
          class="set-input set-input--prose"
          rows="2"
          placeholder="Add context for the audit trail…"
          :disabled="locked"
        />
      </UiField>

      <p v-if="draft.error" class="draft-error" role="alert">{{ draft.error }}</p>
      <p v-if="error" class="draft-error" role="alert">{{ error }}</p>

      <UiButton
        v-if="canAcceptFinal"
        variant="ghost"
        block
        class="btn-gap"
        :disabled="historical"
        @click="emit('riskAccept')"
      >
        <AppIcon name="shield" :size="14" />Risk-accept this CVE…
      </UiButton>
      <UiButton
        variant="primary"
        block
        class="btn-gap"
        :disabled="locked || saving || !draft.body"
        @click="save"
      >
        {{ saving ? 'Saving…' : 'Save to audit trail' }}
      </UiButton>
      <p class="triage-foot">
        <AppIcon name="clock" :size="11" />Every action records who &amp; when. Deadlines absolute, 24h.
      </p>
    </div>
  </aside>
</template>

<style scoped>
.triage {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
/* the B2 slate band — same register as every table head (operator ruling 2026-07-17) */
.triage-head {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 12px 16px;
  font-weight: 600;
  font-size: var(--text-card-title);
  background: var(--table-head-bg);
  color: var(--table-head-fg);
}
.triage-head svg {
  color: var(--coral);
}
.head-state {
  margin-left: auto;
}
.triage-body {
  padding: 16px;
}
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
.triage-undo {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 0 12px;
  padding: 8px 10px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  line-height: 1.45;
}
.triage-locked svg {
  flex: none;
  color: var(--hist-fg);
}
.assignee-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.assignee-val {
  font-size: var(--text-body);
  color: var(--ink);
}
/* nobody owns this finding — the medium-severity chip language, loud enough to notice */
.assignee-none {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--sev-medium-fg);
  background: var(--sev-medium-bg);
  border: 1px solid var(--sev-medium-line);
  border-radius: var(--r-chip);
  padding: 2px 8px;
}
.vex-block {
  margin-top: 2px;
}
.ro-state {
  display: flex;
  gap: 9px;
  align-items: flex-start;
  border-radius: var(--r-sm);
  padding: 10px 12px;
  margin-top: 8px;
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
.presence-note {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 3px;
  margin: 10px 0 4px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--panel);
  border-radius: var(--r-sm);
  padding: 7px 11px;
  line-height: 1.4;
}
.pn-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.pn-fixed {
  background: var(--state-resolved-fg);
}
.pn-stale {
  background: var(--state-stale-fg);
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

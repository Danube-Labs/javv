<script setup lang="ts">
/**
 * The Triage cell next to the head band of a finding (issue 1205, G2 with the quick buttons):
 * Assigned to, the four state buttons, "Note and more…" and Save. FR-7 two-field VEX. The cell
 * owns the one draft; "Note and more…" opens TriageMorePanel in the kit popover with the rest of
 * the form, and the two Save buttons save the same change. Read-only when the user lacks
 * can_triage, and when viewing history (T<now: reconstructed state is not editable). Without
 * can_accept_audit_final the state of a risk-accepted finding is locked too (issue 892); the note
 * and the assignee stay open. Save emits the validated PATCH body: the parent owns the network
 * call and the conflict text. The lines that answer a save (Undo, issue 681, and the save error)
 * stay in the cell; the lines that explain the state are in the panel (operator, 2026-11-16).
 */
import { computed, ref, useTemplateRef, watch } from 'vue'

import StateTag from '@/components/chips/StateTag.vue'
import TriageMorePanel from '@/components/triage/TriageMorePanel.vue'
import TriageStateControl from '@/components/triage/TriageStateControl.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import PopoverShell from '@/components/ui/PopoverShell.vue'
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
const moreOpen = ref(false)

watch(
  () => props.finding.finding_key,
  () => {
    target.value = null
    vexJustification.value = null
    notes.value = ''
    assignee.value = null
    moreOpen.value = false
  },
)

const cell = useTemplateRef<HTMLElement>('cell')
const more = useTemplateRef<InstanceType<typeof UiButton>>('more')
const moreEl = computed(() => (more.value?.$el as HTMLElement | undefined) ?? null)

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
const canSave = computed(() => !locked.value && !props.saving && !!draft.value.body)

function pickState(s: string) {
  if (locked.value || acceptLocked.value) return
  target.value = s
  if (s !== 'not_affected') vexJustification.value = null
  // the reason is in the panel: open it at once (operator, 2026-11-16, question 2 option A)
  else moreOpen.value = true
}
function save() {
  if (!draft.value.body) return
  emit('save', draft.value.body)
  moreOpen.value = false
}
function riskAccept() {
  moreOpen.value = false
  emit('riskAccept')
}
function undoLast() {
  // the picked target is the state being undone: left in place it would read as a pending change
  target.value = null
  vexJustification.value = null
  emit('undo')
}
</script>

<template>
  <aside ref="cell" class="triage">
    <div class="triage-head">
      <AppIcon name="shield" :size="16" /><span>Triage</span>
      <StateTag class="head-state" :state="finding.state" />
    </div>
    <div class="triage-body">
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

      <p v-if="error" class="draft-error" role="alert">{{ error }}</p>

      <div class="cell-actions">
        <UiButton ref="more" :aria-expanded="moreOpen" @click="moreOpen = !moreOpen">Note and more…</UiButton>
        <UiButton variant="primary" :disabled="!canSave" @click="save">
          {{ saving ? 'Saving…' : 'Save to audit trail' }}
        </UiButton>
      </div>
    </div>
  </aside>
  <PopoverShell
    v-if="moreOpen && cell"
    band
    title="Triage"
    :subtitle="finding.cve_id"
    :anchor="cell"
    :trigger="moreEl"
    :width="440"
    @close="moreOpen = false"
  >
    <TriageMorePanel
      v-model:notes="notes"
      v-model:vex-justification="vexJustification"
      :finding="finding"
      :can-triage="canTriage"
      :can-accept-final="canAcceptFinal"
      :historical="historical"
      :locked="locked"
      :accept-locked="acceptLocked"
      :shown-state="shownState"
      :draft-error="draft.error"
      :can-save="canSave"
      :saving="saving"
      @save="save"
      @risk-accept="riskAccept"
    />
  </PopoverShell>
</template>

<style scoped>
.triage {
  display: flex;
  flex-direction: column;
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
  display: flex;
  flex: 1;
  flex-direction: column;
  padding: 16px;
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
.draft-error {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
/* the two buttons sit at the foot of the cell when the head band makes the row taller */
.cell-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-top: auto;
  padding-top: 12px;
}
</style>

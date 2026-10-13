<script setup lang="ts">
/**
 * Bulk triage over the CURRENT LENS (M5d selector contract — a frozen server-side id-set from
 * severity/state/assignee predicates, never a checked-row list). The lens→selector mapping
 * BLOCKS instead of widening (bulkSelector.ts); 413 = selector past the inline cap ("narrow the
 * selection"); one action = one audit row server-side.
 */
import { computed, ref } from 'vue'

import { bulkTriageApiV1FindingsBulkTriagePost } from '@/api/generated'
import TriageStateControl from '@/components/triage/TriageStateControl.vue'
import VexJustificationPicker from '@/components/triage/VexJustificationPicker.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import type { FilterField } from '@/filters/fields.config'
import { lensToSelector } from '@/findings/bulkSelector'
import { buildTriagePatch } from '@/findings/triageRules'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'

const props = defineProps<{
  fields: readonly FilterField[]
  selections: Record<string, string[]>
  modes?: Record<string, 'is' | 'not'>
  /** null while no read for these filters has answered: never show another query's count */
  total: number | null
  canTriage: boolean
  canAcceptFinal: boolean
  historical: boolean
}>()
const emit = defineEmits<{ applied: [count: number] }>()
const clusterStore = useClusterStore()

const open = ref(false)
const target = ref<string | null>(null)
const vexJustification = ref<string | null>(null)
const assignee = ref('')
const notes = ref('')
const submitting = ref(false)
const error = ref<string | null>(null)
const done = ref<number | null>(null)

const lens = computed(() => lensToSelector(props.fields, props.selections, props.modes ?? {}))
const selectorChips = computed(() =>
  lens.value.selector ? Object.entries(lens.value.selector) : [],
)
const draft = computed(() =>
  buildTriagePatch({
    currentState: '__bulk__', // no single current state — any picked target is a change
    targetState: target.value,
    vexJustification: vexJustification.value,
    notes: notes.value,
    assignee: assignee.value.trim() ? assignee.value.trim() : null,
  }),
)

function reset() {
  target.value = null
  vexJustification.value = null
  assignee.value = ''
  notes.value = ''
  error.value = null
  done.value = null
}
function pickState(s: string) {
  target.value = s
  if (s !== 'not_affected') vexJustification.value = null
}

async function apply() {
  if (!draft.value.body || !lens.value.selector || submitting.value) return
  submitting.value = true
  error.value = null
  const response = await bulkTriageApiV1FindingsBulkTriagePost({
    body: {
      cluster_id: clusterStore.selectedId!,
      selector: lens.value.selector,
      patch: draft.value.body,
    },
  })
  submitting.value = false
  if (response.response?.ok && response.data) {
    const count = (response.data as { count: number }).count
    done.value = count
    logger.info('bulk_triage_applied', { count })
    emit('applied', count)
  } else if (response.response?.status === 413) {
    error.value = 'Too many findings match for one bulk action. Narrow the filters.'
  } else if (response.response?.status === 422) {
    error.value = 'The server rejected this patch. Check the state/justification pairing.'
  } else {
    error.value = 'Bulk failed. Check the backend connection.'
    logger.warn('bulk_triage_failed', { status: response.response?.status })
  }
}
</script>

<template>
  <div v-if="canTriage && !historical" class="bulk-wrap">
    <UiButton variant="control" @click="reset(); open = true">
      <AppIcon name="layers" :size="13" />Bulk triage
    </UiButton>

    <ModalShell
      v-if="open"
      title="Bulk triage"
      subtitle="one action, one audit row, for every finding that matches your filters"
      @close="open = false"
    >
      <div>
          <p v-if="lens.blocked" class="bulk-blocked">
            <AppIcon name="alert" :size="13" /> {{ lens.blocked }}
          </p>
          <template v-else>
            <div class="lens-row">
              <span class="lens-label">Filters</span>
              <span v-for="[k, v] in selectorChips" :key="k" class="lens-chip">
                {{ k }} <b>{{ v }}</b>
              </span>
              <span class="lens-count">{{
                total === null ? 'count unknown' : `≈ ${total.toLocaleString('en-US')} findings`
              }}</span>
            </div>

            <UiField label="Set state">
              <TriageStateControl current="__none__" :target="target" @select="pickState" />
            </UiField>
            <div v-if="target === 'not_affected'" class="vex-block">
              <UiField label="Justification · CISA five (required)">
                <VexJustificationPicker :selected="vexJustification" @select="(id) => (vexJustification = id)" />
              </UiField>
            </div>

            <UiField label="Assign to" hint="optional" for="bulk-assignee">
              <input id="bulk-assignee" v-model="assignee" class="fld" type="text" placeholder="username" />
            </UiField>

            <UiField label="Note" hint="one note on every target" for="bulk-notes">
              <textarea id="bulk-notes" v-model="notes" class="fld" rows="2" placeholder="Why this bulk action…" />
            </UiField>

            <p v-if="draft.error" class="bulk-error" role="alert">{{ draft.error }}</p>
            <p v-if="error" class="bulk-error" role="alert">{{ error }}</p>
            <p v-if="done !== null" class="bulk-done">
              <AppIcon name="check" :size="13" /> Applied to {{ done }} finding(s), one audit row.
            </p>
          </template>
      </div>
      <template #actions>
          <!-- a blocked dialog has nothing to apply: one way out, not a dead primary beside it -->
          <UiButton variant="ghost" @click="open = false">{{ done !== null || lens.blocked ? 'Close' : 'Cancel' }}</UiButton>
          <UiButton
            v-if="done === null && !lens.blocked"
            variant="primary"
            :disabled="!draft.body || submitting || total === null"
            @click="apply"
          >
            {{ submitting ? 'Applying…' : 'Apply to matching findings' }}
          </UiButton>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.bulk-wrap {
  display: inline-flex;
}
.bulk-blocked {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin: 0;
  font-size: var(--text-body);
  color: var(--ink);
  background: var(--hist-bg);
  border: 1px solid var(--hist-line);
  border-radius: var(--r-sm);
  padding: 10px 12px;
  line-height: 1.5;
}
.bulk-blocked svg {
  flex: none;
  margin-top: 2px;
  color: var(--hist-fg);
}
.lens-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  padding: 9px 11px;
}
.lens-label {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--soft);
}
.lens-chip {
  font-size: var(--text-sm);
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-chip);
  padding: 3px 8px;
  color: var(--ink);
}
.lens-count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
.fld {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 8px 10px;
  font-family: var(--font-ui);
  font-size: var(--text-mono-cell);
  color: var(--ink);
  background: var(--card);
  outline: none;
  resize: vertical;
  box-sizing: border-box;
}
.fld:focus {
  border-color: var(--coral);
}
.vex-block {
  margin-top: 2px;
}
.bulk-error {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
.bulk-done {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 10px 0 0;
  font-size: var(--text-body);
  color: var(--state-resolved-fg);
}
</style>

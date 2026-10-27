<script setup lang="ts">
/**
 * Scoped risk-accept (prototype `RiskAcceptDialog` on tokens) — creates an IMMUTABLE decision
 * (D40: edits later are revoke+new; `expiry` can never change). Scope chips are seeded from the
 * finding being viewed (its image and namespaces); empty scope = cluster-wide, and the blast
 * radius line says so before the operator commits. `apply_both_scanners` is D22's pinned
 * semantics — a scanner-specific decision names its scanner.
 */
import { computed, ref } from 'vue'

import { createApiV1DecisionsPost } from '@/api/generated'
import { EXPIRY_PASSED_TYPE } from '@/api/problem'
import { EXPIRY_REFUSED, firstExpiryDate } from '@/approvals/viewModel'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { useApi } from '@/composables/useApi'
import { logger } from '@/lib/logger'
import type { FindingRow } from '@/stores/findings'

const props = defineProps<{ cveId: string; finding: FindingRow }>()
const emit = defineEmits<{ close: []; created: [] }>()
const { withGlobals } = useApi()

const image = computed(() => `${props.finding.image_repo}${props.finding.tag ? ':' + props.finding.tag : ''}`)
const namespaces = computed(() =>
  Array.isArray(props.finding.namespaces) ? (props.finding.namespaces as string[]) : [],
)

const nsSel = ref<Set<string>>(new Set())
const imgSel = ref<Set<string>>(new Set())
const applyTo = ref<'both' | 'trivy' | 'grype'>('both')
const APPLY_OPTS = [
  { value: 'both', label: 'Both scanners' },
  { value: 'trivy', label: 'trivy only' },
  { value: 'grype', label: 'grype only' },
] as const
const expiry = ref('')
const justification = ref('')
const submitting = ref(false)
const error = ref<string | null>(null)

function toggle(set: Set<string>, v: string) {
  if (set.has(v)) set.delete(v)
  else set.add(v)
}
const clusterWide = computed(() => nsSel.value.size === 0 && imgSel.value.size === 0)
// a date before it is refused by the server; the field's `min` alone does not stop a typed one
const minExpiry = firstExpiryDate(Date.now())
const expiryOk = computed(() => expiry.value === '' || expiry.value >= minExpiry)
const valid = computed(() => justification.value.trim().length > 0 && expiryOk.value)

async function submit() {
  if (!valid.value || submitting.value) return
  // withGlobals throws when no cluster is selected — resolve it BEFORE arming the busy flag,
  // or a throw here would strand the dialog at "Saving…" (issue 509's defect class)
  const globals = withGlobals()
  submitting.value = true
  error.value = null
  const response = await createApiV1DecisionsPost({
    body: {
      type: 'risk_accepted',
      cve_id: props.cveId,
      scope: { namespaces: [...nsSel.value], images: [...imgSel.value] },
      apply_both_scanners: applyTo.value === 'both',
      ...(applyTo.value === 'both' ? {} : { scanner: applyTo.value }),
      justification: justification.value.trim(),
      ...(expiry.value ? { expiry: expiry.value } : {}),
      cluster_id: globals.cluster_id,
    },
  })
  submitting.value = false
  if (response.response?.ok) {
    logger.info('decision_created', { cve_id: props.cveId, type: 'risk_accepted' })
    emit('created')
    emit('close')
  } else {
    const status = response.response?.status
    error.value =
      status === 403
        ? 'Only a Security Lead or an admin can accept a risk.'
        : (response.error as { type?: unknown } | undefined)?.type === EXPIRY_PASSED_TYPE
          ? EXPIRY_REFUSED
          : 'Could not create the decision. Check the backend connection.'
    logger.warn('decision_create_failed', { status })
  }
}

</script>

<template>
  <ModalShell title="Risk-accept this CVE" :subtitle="cveId" :width="560" @close="emit('close')">
      <div>
        <div class="ra-anchor">
          <span class="mono-cell strong">{{ cveId }}</span>
          <span class="ra-anchor-note">A decision anchors on the CVE + scope, so a package bump auto-inherits it.</span>
        </div>

        <UiField label="Scope · namespaces" hint="none selected = cluster-wide">
          <div class="ra-chips">
            <span v-if="namespaces.length === 0" class="ra-none">no namespaces on this finding</span>
            <button
              v-for="ns in namespaces"
              :key="ns"
              type="button"
              class="ra-chip"
              :class="{ 'ra-chip-on': nsSel.has(ns) }"
              @click="toggle(nsSel, ns)"
            >
              {{ ns }}
            </button>
          </div>
        </UiField>

        <UiField label="Scope · images">
          <div class="ra-chips">
            <button
              type="button"
              class="ra-chip mono-cell"
              :class="{ 'ra-chip-on': imgSel.has(image) }"
              @click="toggle(imgSel, image)"
            >
              {{ image }}
            </button>
          </div>
        </UiField>

        <div class="ra-blast">
          <AppIcon name="layers" :size="14" />
          <span>
            Blast radius:
            <b v-if="clusterWide">cluster-wide, every image</b>
            <b v-else>{{ imgSel.size }} image(s) + {{ nsSel.size }} namespace(s)</b>
            <em v-if="clusterWide || nsSel.size > 0"> · namespace/cluster scope auto-applies to NEW matching findings</em>
            <em v-else> · image scope does not cascade to new images</em>
          </span>
        </div>

        <div class="fld-2">
          <UiField label="Expiry" :hint="expiryOk ? 'immutable: change = revoke + new' : EXPIRY_REFUSED" for="ra-expiry">
            <input id="ra-expiry" v-model="expiry" class="fld" type="date" :min="minExpiry" :aria-invalid="!expiryOk" />
          </UiField>
          <UiField label="Apply to">
            <UiSegControl v-model="applyTo" :options="APPLY_OPTS" label="Apply to" />
          </UiField>
        </div>

        <UiField label="Justification (required)" for="ra-just">
          <textarea
            id="ra-just"
            v-model="justification"
            class="fld"
            rows="3"
            placeholder="Why is this risk acceptable, and for how long?"
          />
        </UiField>

        <p class="ra-note">
          <AppIcon name="info" :size="12" />
          Decisions are immutable. Editing later revokes and re-creates; the old one stays in history.
        </p>
        <p v-if="error" class="ra-error" role="alert">{{ error }}</p>
      </div>

      <template #actions>
        <UiButton variant="ghost" @click="emit('close')">Cancel</UiButton>
        <UiButton variant="primary" :disabled="!valid || submitting" @click="submit">
          {{ submitting ? 'Creating…' : 'Create decision' }}
        </UiButton>
      </template>
  </ModalShell>
</template>

<style scoped>
.ra-anchor {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  padding: 9px 12px;
  margin-bottom: 4px;
}
.ra-anchor-note {
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.4;
}
.ra-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ra-none {
  font-size: var(--text-sm);
  color: var(--soft);
}
.ra-chip {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: var(--r-chip);
  padding: 5px 10px;
  font-size: var(--text-control);
  font-family: var(--font-ui);
  color: var(--ink);
  cursor: default;
}
.ra-chip:hover {
  border-color: var(--control-hover-line);
}
.ra-chip-on {
  border-color: var(--coral);
  background: var(--dd-on-bg);
  box-shadow: inset 0 0 0 1px var(--coral);
}
.ra-blast {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--panel);
  border-radius: var(--r-sm);
  padding: 9px 11px;
  line-height: 1.45;
}
.ra-blast svg {
  flex: none;
  margin-top: 1px;
  color: var(--teal);
}
.ra-blast em {
  font-style: normal;
  color: var(--soft);
}
.fld-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
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
.ra-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.45;
}
.ra-note svg {
  flex: none;
}
.ra-error {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--health-down-fg);
}
.mono-cell {
  font-family: var(--font-mono);
}
.strong {
  font-weight: 700;
}
</style>

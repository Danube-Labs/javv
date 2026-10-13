<script setup lang="ts">
/**
 * Finding detail (M9b slice 2 + 3; split into panels per audit F-15 — this view owns the
 * ORCHESTRATION: route identity, the four fetches, the triage PATCH + conflict surfacing,
 * dialog state. Presentation lives in components/finding/*). Identity = (cve_id,
 * image_digest); the pair query carries NO scanner filter — the returned rows ARE the
 * per-scanner evidence (A-3, never reconciled). Historical rows null fields out —
 * everything here tolerates that.
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  readAuditLogApiV1AuditGet,
  listDecisionsApiV1DecisionsGet,
  revokeApiV1DecisionsDecisionIdRevokePost,
  searchFindingsApiV1FindingsGet,
  triageApiV1FindingsFindingKeyTriagePatch,
} from '@/api/generated'
import type { SearchFindingsApiV1FindingsGetData } from '@/api/generated'
import ActivityCard, { type ActivityRow } from '@/components/finding/ActivityCard.vue'
import AffectedCard from '@/components/finding/AffectedCard.vue'
import DetailHead from '@/components/finding/DetailHead.vue'
import EvidenceCard from '@/components/finding/EvidenceCard.vue'
import DecisionsCard, { type DecisionRow } from '@/components/triage/DecisionsCard.vue'
import RiskAcceptDialog from '@/components/triage/RiskAcceptDialog.vue'
import TriagePanel from '@/components/triage/TriagePanel.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useApi } from '@/composables/useApi'
import {
  affectedComponentRows,
  epssOf,
  kevOn,
  primaryRow,
  SCANNER_ORDER,
  scopeToPackage,
  severityDisagrees,
  type AffectedComponentRow,
} from '@/findings/detailViewModel'
import { readFailureCopy } from '@/findings/failureCopy'
import { undoPatch, type TriagePatchBody } from '@/findings/triageRules'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import type { FindingRow } from '@/stores/findings'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()
const auth = useAuthStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()
const { withGlobals } = useApi()

const cveId = computed(() => String(route.params.cveId ?? ''))
const digest = computed(() => (typeof route.query.digest === 'string' ? route.query.digest : null))
const clickedScanner = computed(() =>
  typeof route.query.scanner === 'string' ? route.query.scanner : null,
)

const rows = ref<FindingRow[]>([])
const affected = ref<AffectedComponentRow[]>([])
const affectedTruncated = ref(false)
const affectedFailed = ref(false)
const loading = ref(true)
const failed = ref(false)
const failedStatus = ref<number | null>(null)

/* ---- the sibling pair: one query, no scanner filter (A-3) ---- */
const pairQuery = computed(() =>
  clusterStore.selectedId && cveId.value && digest.value
    ? withGlobals({ cve_id: cveId.value, image_digest: digest.value, size: 10 })
    : null,
)

let pairSeq = 0
watch(
  pairQuery,
  async (q, old) => {
    if (!q || JSON.stringify(q) === JSON.stringify(old)) return
    const mine = ++pairSeq
    loading.value = true
    const response = await searchFindingsApiV1FindingsGet({
      query: q as SearchFindingsApiV1FindingsGetData['query'],
    })
    if (mine !== pairSeq) return // a newer read owns the page now
    loading.value = false
    if (response.response?.ok && response.data) {
      rows.value = (response.data as { data: FindingRow[] }).data
      failed.value = false
    } else {
      failed.value = true
      failedStatus.value = response.response?.status ?? null
      logger.warn('finding_detail_failed', { status: response.response?.status })
    }
  },
  { immediate: true },
)

/* ---- affected components: every occurrence of the CVE, server-side filtered ---- */
const occQuery = computed(() =>
  clusterStore.selectedId && cveId.value
    ? withGlobals({ cve_id: cveId.value, size: 200 })
    : null,
)

let occSeq = 0
watch(
  occQuery,
  async (q, old) => {
    if (!q || JSON.stringify(q) === JSON.stringify(old)) return
    const mine = ++occSeq
    const response = await searchFindingsApiV1FindingsGet({
      query: q as SearchFindingsApiV1FindingsGetData['query'],
    })
    if (mine !== occSeq) return // a newer read owns the card now
    affectedFailed.value = !response.response?.ok || !response.data
    if (!affectedFailed.value) {
      const body = response.data as { data: FindingRow[]; total: number }
      affected.value = affectedComponentRows(body.data)
      affectedTruncated.value = body.total > body.data.length
    } else {
      affected.value = []
      affectedTruncated.value = false
      logger.warn('finding_occurrences_failed', { status: response.response?.status })
    }
  },
  { immediate: true },
)

/* ---- view-model: everything reads the PACKAGE-scoped set (one row per scanner) ---- */
const pkg = computed(() => (typeof route.query.pkg === 'string' ? route.query.pkg : null))
const ver = computed(() =>
  typeof route.query.ver === 'string' && route.query.ver ? route.query.ver : null,
)
const scope = computed(() => scopeToPackage(rows.value, pkg.value, ver.value))
const evidence = computed(() => scope.value.scoped)
const otherPackages = computed(() => scope.value.otherPackages)
const primary = computed(() => primaryRow(evidence.value, clickedScanner.value))
const kev = computed(() => kevOn(evidence.value))
const epss = computed(() => epssOf(evidence.value))
const disagrees = computed(() => severityDisagrees(evidence.value))
const missingScanners = computed(() =>
  SCANNER_ORDER.filter((s) => !evidence.value.some((r) => r.scanner === s)),
)

function goBack() {
  if (window.history.state?.back) router.back()
  else void router.push({ name: 'findings' })
}

/* ---- triage (FR-7): the panel validates, this owns the PATCH + conflict surfacing ---- */
const saving = ref(false)
const triageError = ref<string | null>(null)
const historical = computed(() => timeTravel.t !== null)

/** The last saved state change, with the body that takes it back. Offered while the finding is
 * still in the state that change left it in. */
const lastChange = ref<{ key: string; from: string; to: string; body: TriagePatchBody } | null>(null)
const undoOffer = computed(() => {
  const c = lastChange.value
  return c && c.key === primary.value?.finding_key && c.to === primary.value.state ? c : null
})
function undoTriage() {
  if (undoOffer.value) void saveTriage(undoOffer.value.body, true)
}

async function saveTriage(body: TriagePatchBody, undoing = false) {
  const before = primary.value
  const key = before?.finding_key
  if (!key) return
  saving.value = true
  triageError.value = null
  const response = await triageApiV1FindingsFindingKeyTriagePatch({
    path: { finding_key: key },
    body,
  })
  saving.value = false
  if (response.response?.ok && response.data) {
    const updated = (response.data as { finding: FindingRow }).finding
    rows.value = rows.value.map((r) => (r.finding_key === key ? { ...r, ...updated } : r))
    logger.info('triage_saved', { finding_key: key, state: updated.state, undo: undoing })
    if (undoing) {
      lastChange.value = null
    } else if (updated.state !== before.state) {
      const back = undoPatch(
        { state: before.state, vex_justification: before.vex_justification as string | null },
        updated.state,
      )
      lastChange.value = back ? { key, from: before.state, to: updated.state, body: back } : null
    }
    toast.success(undoing ? 'Change undone' : 'Triage saved')
  } else if (response.response?.status === 409) {
    triageError.value = 'Changed by someone else. Reload and retry.'
  } else if (response.response?.status === 422) {
    triageError.value = 'The server rejected this transition. Reload and retry.'
    logger.warn('triage_rejected', { status: 422 })
  } else {
    triageError.value = 'Save failed. Check the backend connection.'
    logger.warn('triage_failed', { status: response.response?.status })
  }
}

/* ---- decisions on this CVE (immutable; revoked stay struck-through) ---- */
const raOpen = ref(false)
const decisions = ref<DecisionRow[]>([])
const decisionsBusy = ref(false)
const decisionsFailed = ref(false)

let decisionsSeq = 0
async function fetchDecisions() {
  if (!clusterStore.selectedId || !cveId.value) return
  const mine = ++decisionsSeq
  const response = await listDecisionsApiV1DecisionsGet({
    query: {
      cluster_id: clusterStore.selectedId,
      cve_id: cveId.value,
      include_revoked: true,
    },
  })
  if (mine !== decisionsSeq) return // a newer read owns the card now
  decisionsFailed.value = !response.response?.ok || !response.data
  if (!decisionsFailed.value) {
    decisions.value = (response.data as { decisions: DecisionRow[] }).decisions ?? []
  } else {
    decisions.value = [] // another CVE's, or an unknown list: never shown as this one's
    logger.warn('decisions_list_failed', { status: response.response?.status })
  }
}
watch([cveId, () => clusterStore.selectedId], () => void fetchDecisions(), { immediate: true })

async function revokeDecision(id: string) {
  decisionsBusy.value = true
  const response = await revokeApiV1DecisionsDecisionIdRevokePost({ path: { decision_id: id } })
  decisionsBusy.value = false
  if (response.response?.ok) {
    logger.info('decision_revoked', { decision_id: id })
    toast.success('Decision revoked')
    await fetchDecisions()
    void fetchActivity()
  } else {
    logger.warn('decision_revoke_failed', { status: response.response?.status })
  }
}

function onDecisionCreated() {
  toast.success('Decision recorded')
  void fetchDecisions()
  void fetchActivity()
}

/* ---- per-finding activity (the audit trail rows for THIS finding_key) ---- */
const activity = ref<ActivityRow[]>([])
const activityFailed = ref(false)

let activitySeq = 0
async function fetchActivity() {
  const p = primary.value
  if (!p || !clusterStore.selectedId) return
  const mine = ++activitySeq
  const response = await readAuditLogApiV1AuditGet({
    query: {
      cluster_id: clusterStore.selectedId,
      finding_key: p.finding_key,
      size: 50,
    } as never,
  })
  if (mine !== activitySeq) return // a newer read owns the card now
  activityFailed.value = !response.response?.ok || !response.data
  if (!activityFailed.value) {
    activity.value = (response.data as { data: ActivityRow[] }).data
  } else {
    activity.value = []
    logger.warn('finding_activity_failed', { status: response.response?.status })
  }
}
watch([primary, () => clusterStore.selectedId], () => void fetchActivity(), { immediate: true })
</script>

<template>
  <div class="screen">
    <button class="back-link" @click="goBack"><AppIcon name="arrowback" :size="15" />Findings</button>

    <!-- loading: skeletons, not spinners -->
    <div v-if="loading" class="skel-stack" aria-busy="true" aria-label="Loading finding">
      <UiSkeleton :height="112" />
      <UiSkeleton :height="180" />
      <UiSkeleton :height="180" />
    </div>

    <p v-else-if="failed" class="load-error" role="alert">
      {{ readFailureCopy(failedStatus, 'Finding unavailable. Check the backend connection.') }}
    </p>

    <div v-else-if="!digest" class="not-found">
      <h1 class="mono">{{ cveId }}</h1>
      <p>This link is missing the image identity. Open the finding from the grid.</p>
    </div>

    <div v-else-if="rows.length === 0" class="not-found">
      <h1 class="mono">{{ cveId }}</h1>
      <p>
        No current finding for this CVE on this image. It may have been resolved by a newer
        scan, or the selected range ends before it was first seen.
      </p>
    </div>

    <template v-else>
      <DetailHead
        :cve-id="cveId"
        :primary="primary"
        :digest="digest"
        :kev="kev"
        :disagrees="disagrees"
        :epss="epss"
      />

      <!-- issue-434 ruling: evidence reads left, everything actionable/journal lives in the
           rail — no full-width cards dangling below the fold -->
      <div class="detail-grid">
        <EvidenceCard
          class="detail-main"
          :evidence="evidence"
          :missing-scanners="missingScanners"
          :disagrees="disagrees"
          :other-packages="otherPackages"
        />

        <div class="detail-rail">
          <TriagePanel
            v-if="primary"
            :finding="primary"
            :can-triage="auth.hasCapability('can_triage')"
            :can-accept-final="auth.hasCapability('can_accept_audit_final')"
            :historical="historical"
            :saving="saving"
            :error="triageError"
            :current-user="auth.user?.username ?? null"
            :undo="undoOffer"
            @save="saveTriage"
            @undo="undoTriage"
            @risk-accept="raOpen = true"
          />
        </div>

        <!-- row 2, same tracks, stretched — decisions and activity sit side by side at
             equal height (operator, 2026-07-17); the pagers bound their growth -->
        <DecisionsCard
          class="detail-main"
          :decisions="decisions"
          :can-accept-final="auth.hasCapability('can_accept_audit_final')"
          :busy="decisionsBusy"
          :failed="decisionsFailed"
          @create="raOpen = true"
          @revoke="revokeDecision"
        />
        <ActivityCard :activity="activity" :failed="activityFailed" />
      </div>

      <!-- the widest table gets the full width, below the grid, same edges -->
      <AffectedCard
        class="detail-band"
        :affected="affected"
        :truncated="affectedTruncated"
        :failed="affectedFailed"
      />

      <RiskAcceptDialog
        v-if="raOpen && primary"
        :cve-id="cveId"
        :finding="primary"
        @close="raOpen = false"
        @created="onDecisionCreated"
      />
    </template>
  </div>
</template>

<style scoped>
.back-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: var(--soft);
  font-size: var(--text-sm);
  font-family: var(--font-ui);
  padding: 0 0 14px;
  cursor: default;
}
.back-link:hover {
  color: var(--coral-text);
}

.detail-grid {
  display: grid;
  grid-template-columns: 1.55fr 1fr;
  gap: var(--space-4);
  /* both tracks stretch to the row: evidence and triage are the same height by
     construction — no dead space under either (operator, 2026-07-17) */
  align-items: stretch;
  margin-top: var(--space-6); /* the header is its own band — give it air below */
}
.detail-main {
  min-width: 0;
}
@media (max-width: 1180px) {
  .detail-grid {
    grid-template-columns: 1fr;
  }
}
/* full-width sections below the grid — same edges as the grid, same rhythm */
.detail-band {
  margin-top: var(--space-4);
}
.detail-rail {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.not-found h1 {
  font-family: var(--font-mono);
}
.not-found p {
  color: var(--soft);
  max-width: 62ch;
}
.load-error {
  color: var(--health-down-fg);
  font-size: var(--text-body);
}

.skel-stack > * + * {
  margin-top: 16px;
}
</style>

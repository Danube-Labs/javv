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

import { closeUnpaged } from '@/api/cursors'
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
import { usePackagesOnImage } from '@/composables/usePackagesOnImage'
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

/* the package and version of the link: the row that the user opened */
const pkg = computed(() => (typeof route.query.pkg === 'string' ? route.query.pkg : null))
const ver = computed(() =>
  typeof route.query.ver === 'string' && route.query.ver ? route.query.ver : null,
)

/* ---- the sibling pair: one query, no scanner filter (A-3) ---- */
const pairQuery = computed(() =>
  clusterStore.selectedId && cveId.value && digest.value
    ? withGlobals({
        cve_id: [cveId.value],
        image_digest: digest.value,
        // the package of the link, so its rows are always in the read (issue 1227)
        ...(pkg.value ? { package_name: [pkg.value] } : {}),
        size: 10,
      })
    : null,
)

let pairSeq = 0
async function loadPair(q: NonNullable<typeof pairQuery.value>) {
  const mine = ++pairSeq
  const response = await searchFindingsApiV1FindingsGet({
    query: q as SearchFindingsApiV1FindingsGetData['query'],
  })
  closeUnpaged(response.data?.next_cursor, !q.as_of) // one page only: never paged
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
}
watch(
  pairQuery,
  async (q, old) => {
    if (!q) {
      // a link without the image never reads: show what is missing instead of loading for ever
      if (!digest.value) loading.value = false
      return
    }
    if (JSON.stringify(q) === JSON.stringify(old)) return
    loading.value = true
    await loadPair(q)
  },
  { immediate: true },
)

/** A decision changes the state of the finding on the server at once: read it again, in place. */
function reloadPair() {
  if (pairQuery.value) void loadPair(pairQuery.value)
}

/* ---- affected components: every occurrence of the CVE, server-side filtered ---- */
const occQuery = computed(() =>
  clusterStore.selectedId && cveId.value
    ? withGlobals({ cve_id: [cveId.value], size: 200, locations: true }) // the Paths column, issue 1077
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
    closeUnpaged(response.data?.next_cursor, !q.as_of) // one page only: never paged
    if (mine !== occSeq) return // a newer read owns the card now
    affectedFailed.value = !response.response?.ok || !response.data
    if (!affectedFailed.value) {
      const body = response.data as { data: FindingRow[]; total: { value: number } }
      affected.value = affectedComponentRows(body.data)
      affectedTruncated.value = body.total.value > body.data.length
    } else {
      affected.value = []
      affectedTruncated.value = false
      logger.warn('finding_occurrences_failed', { status: response.response?.status })
    }
  },
  { immediate: true },
)

/* each package of this CVE on this image, for the package menu of the head band (issue 1227) */
const { packages, cut: packagesCut } = usePackagesOnImage(cveId, digest)

/* ---- view-model: everything reads the PACKAGE-scoped set (one row per scanner) ---- */
const evidence = computed(() => scopeToPackage(rows.value, pkg.value, ver.value))
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
    triageError.value = 'Another person changed this finding. Load the page again. Then save your change again.'
  } else if (response.response?.status === 422) {
    triageError.value = 'JAVV did not accept this change of state. Load the page again. Then try again.'
    logger.warn('triage_rejected', { status: 422 })
  } else {
    triageError.value = 'JAVV did not save the change. The backend did not answer, or it sent an error. Try again.'
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
    reloadPair()
    await fetchDecisions()
    void fetchActivity()
  } else {
    logger.warn('decision_revoke_failed', { status: response.response?.status })
  }
}

function onDecisionCreated() {
  toast.success('Decision recorded')
  reloadPair()
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
  closeUnpaged(response.data?.next_cursor, true) // one page only: never paged
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

    <div v-else-if="evidence.length === 0" class="not-found">
      <h1 class="mono">{{ cveId }}</h1>
      <!-- a link that names a package says which one it looked for: the CVE can still be on the
           image in other packages (issue 1227) -->
      <p v-if="pkg">
        This image has no finding of {{ cveId }} in {{ pkg }}{{ ver ? ` ${ver}` : '' }} at the selected
        time. A newer scan may no longer report it. Or the selected time range may end before a scan
        found it.
      </p>
      <p v-else>
        No current finding for this vulnerability on this image. It may have been resolved by a newer
        scan, or the selected range ends before it was first seen.
      </p>
    </div>

    <template v-else>
      <!-- issue 1205: the head band, the evidence and the Triage cell share the first row; the
           cards follow at full width, Decisions and Activity side by side -->
      <div class="head-row">
        <DetailHead
          :cve-id="cveId"
          :primary="primary"
          :digest="digest"
          :kev="kev"
          :disagrees="disagrees"
          :epss="epss"
          :packages="packages"
          :packages-cut="packagesCut"
        />
        <EvidenceCard
          class="head-ev"
          :evidence="evidence"
          :missing-scanners="missingScanners"
          :disagrees="disagrees"
        />
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

      <AffectedCard
        class="detail-band"
        :affected="affected"
        :truncated="affectedTruncated"
        :cve-id="cveId"
        :cluster-name="clusterStore.selected?.cluster_name ?? clusterStore.selectedId ?? ''"
        :failed="affectedFailed"
      />

      <div class="card-pair detail-band">
        <DecisionsCard
          :decisions="decisions"
          :can-accept-final="auth.hasCapability('can_accept_audit_final')"
          :can-triage="auth.hasCapability('can_triage')"
          :busy="decisionsBusy"
          :failed="decisionsFailed"
          @create="raOpen = true"
          @revoke="revokeDecision"
        />
        <ActivityCard :activity="activity" :failed="activityFailed" />
      </div>

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

/* three panels (operator, 2026-11-16): the head band, the evidence and the Triage cell; the
   evidence goes under them below 1280 px, and all three stack below 1180 px */
.head-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 300px;
  grid-template-areas: 'head ev triage';
  gap: var(--space-4);
  align-items: stretch;
}
.head-row > :deep(.detail-head) {
  grid-area: head;
}
.head-ev {
  grid-area: ev;
  min-width: 0;
}
/* TriagePanel has two roots (the cell and its popover), so this page's scope does not reach it */
.head-row > :deep(.triage) {
  grid-area: triage;
}
.card-pair {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: var(--space-4);
  align-items: stretch;
}
@media (max-width: 1279px) {
  .head-row {
    grid-template-columns: minmax(0, 1fr) 300px;
    grid-template-areas: 'head triage' 'ev ev';
  }
}
@media (max-width: 1180px) {
  .head-row {
    grid-template-columns: minmax(0, 1fr);
    grid-template-areas: 'head' 'triage' 'ev';
  }
  .card-pair {
    grid-template-columns: minmax(0, 1fr);
  }
}
.detail-band {
  margin-top: var(--space-4);
}

.not-found h1 {
  font-family: var(--font-mono);
}
.not-found p {
  color: var(--soft);
  max-width: 62ch;
}

.skel-stack > * + * {
  margin-top: 16px;
}
</style>

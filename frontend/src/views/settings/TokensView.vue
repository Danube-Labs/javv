<script setup lang="ts">
/**
 * Access & tokens panel (§13.5; prototype screens-config.jsx `access` section, push-tokens
 * table): the can_manage_tokens surface over scanner push tokens. The raw token appears exactly
 * ONCE — in the mint/rotate response modal — and is never recoverable (copy affordance +
 * "you won't see this again"). Revoke disables (ingest 401s next push); rotate mints the
 * sibling first so the scanner is never token-less (it inherits the old expiry). All mutations
 * are journaled server-side. Cross-cluster listing is BY DESIGN (D38 MVP tenancy).
 * The table rides the shared tbl-card + GridPager grammar (pages are display slices of the
 * one server answer, the ScannerRunsTable idiom). Prototype deltas (ruled, row 7): no
 * registries/imagePullSecrets rows (post-MVP settings issue), no static transport row;
 * optional expiry at mint (task E m-7) via the shared UiDateTime calendar pair. Retired clusters
 * (issue 765) are listed apart in the mint picker: a scan on a new token brings one back, as the
 * retire confirm says (operator ruling 2026-10-07).
 */
import { computed, ref } from 'vue'

import {
  listTokensApiV1AdminTokensGet,
  mintApiV1AdminTokensPost,
  revokeApiV1AdminTokensTokenIdRevokePost,
  rotateApiV1AdminTokensTokenIdRotatePost,
} from '@/api/generated'
import { client } from '@/api/client'
import DotWord from '@/components/chips/DotWord.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import GridPager from '@/components/findings/GridPager.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDateTime from '@/components/ui/UiDateTime.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'

import { useFleetClusters } from './clusterRetirement'
import {
  CLUSTER_ID_PROBLEM,
  mintClusterId,
  mintExpiry,
  NEW_CLUSTER,
  TOKEN_STATUS_TONE,
  tokenStatus,
  type TokenRow,
} from './tokensForm'

const clusterStore = useClusterStore()
const toast = useToastStore()

const rows = ref<TokenRow[]>([])
const total = ref(0)
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

const LIST_SIZE = 100 // the endpoint's page cap default — an MVP token inventory fits one page

async function load() {
  loading.value = true
  const { data, response } = await listTokensApiV1AdminTokensGet({
    client,
    query: { size: LIST_SIZE },
  })
  loading.value = false
  failed.value = !response?.ok || !data
  if (failed.value) {
    logger.warn('tokens_load_failed', { status: response?.status })
    return
  }
  const body = data as { tokens: TokenRow[]; total: number }
  rows.value = body.tokens
  total.value = body.total
}
void load()

// the switcher's list leaves retired clusters out; this one has them, for names and minting
const fleet = useFleetClusters()
void fleet.load()
const activeClusters = computed(() => fleet.rows.value.filter((c) => !c.retired))
// a cluster whose delete did not finish is not offered: a scan on a new token would bring it back
// with part of its data gone (issue 778)
const retiredClusters = computed(() => fleet.rows.value.filter((c) => c.retired && !c.delete_started))

const now = () => new Date()

// display slices of the one server answer (the ScannerRunsTable idiom)
const page = ref(0)
const size = ref(10)
const shown = computed(() => rows.value.slice(page.value * size.value, (page.value + 1) * size.value))
const hasNext = computed(() => (page.value + 1) * size.value < rows.value.length)
function setSize(next: number) {
  size.value = next
  page.value = 0
}

const clusterName = (id: string) =>
  clusterStore.clusters.find((c) => c.cluster_id === id)?.cluster_name ??
  fleet.rows.value.find((c) => c.cluster_id === id)?.cluster_name ??
  id

// ── mint ────────────────────────────────────────────────────────────────────────────────
const mintOpen = ref(false)
const mintCluster = ref('')
const mintNewId = ref('')
const mintScanner = ref('trivy')
const mintExpiryParts = ref({ date: '', time: '' }) // both empty = non-expiring token
const mintError = ref('')
const SCANNER_OPTS = [
  { value: 'trivy', label: 'trivy' },
  { value: 'grype', label: 'grype' },
]

const mintExpiryInvalid = computed(() => mintExpiry(mintExpiryParts.value, now()).kind === 'invalid')
const mintRetired = computed(() => retiredClusters.value.find((c) => c.cluster_id === mintCluster.value) ?? null)
const mintTarget = computed(() => mintClusterId(mintCluster.value, mintNewId.value))
// said once something is typed: an empty field is unfinished, not wrong
const mintIdProblem = computed(() =>
  mintCluster.value === NEW_CLUSTER && mintNewId.value.trim() !== '' && mintTarget.value === null
    ? CLUSTER_ID_PROBLEM
    : null,
)
const CLUSTER_ID_COMMAND = "kubectl get namespace kube-system -o jsonpath='{.metadata.uid}'"

function openMint() {
  // a cluster is listed once its first token exists, so a new one can only be typed in
  mintCluster.value = clusterStore.selectedId ?? clusterStore.clusters[0]?.cluster_id ?? NEW_CLUSTER
  mintNewId.value = ''
  mintScanner.value = 'trivy'
  mintExpiryParts.value = { date: '', time: '' }
  mintError.value = ''
  mintOpen.value = true
  void fleet.load()
}

// the raw-token-once modal (mint AND rotate land here)
const minted = ref<{ id: string; token: string } | null>(null)
const copied = ref(false)

async function submitMint() {
  const expiry = mintExpiry(mintExpiryParts.value, now())
  const clusterId = mintTarget.value
  if (clusterId === null || expiry.kind === 'invalid') return
  const isNew = mintCluster.value === NEW_CLUSTER
  busy.value = true
  const { data, response } = await mintApiV1AdminTokensPost({
    client,
    body: {
      cluster_id: clusterId,
      scanner: mintScanner.value,
      ...(expiry.kind === 'iso' ? { expiry: expiry.iso } : {}),
    },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('token_mint_failed', { status: response?.status })
    mintError.value =
      response?.status === 403
        ? 'Minting needs the can_manage_tokens capability.'
        : 'Minting failed. No token was created.'
    return
  }
  mintOpen.value = false
  copied.value = false
  showMinted(data)
  await load()
  // the token is what lists a new cluster: show it in the switcher now, not after a reload
  if (isNew) await Promise.all([clusterStore.refresh(), fleet.load()])
}

// the token exists once the reply is OK, but its value arrives only in the body: a reply whose body
// never arrived leaves a token nobody can copy, and rotating it is the way to a new value
function showMinted(data: unknown) {
  if (data) {
    minted.value = data as { id: string; token: string }
    return
  }
  logger.warn('token_value_lost')
  toast.error('The token was created, but its value did not reach this page. Rotate it to get a value you can copy.')
}

async function copyToken() {
  if (minted.value === null) return
  await navigator.clipboard.writeText(minted.value.token)
  copied.value = true
}

// ── rotate / revoke (confirm-first — both are destructive to the OLD token) ────────────
const confirmAction = ref<{ kind: 'rotate' | 'revoke'; row: TokenRow } | null>(null)

async function runConfirmed() {
  const action = confirmAction.value
  if (action === null) return
  busy.value = true
  const call =
    action.kind === 'rotate' ? rotateApiV1AdminTokensTokenIdRotatePost : revokeApiV1AdminTokensTokenIdRevokePost
  const { data, response } = await call({ client, path: { token_id: action.row.id } })
  busy.value = false
  confirmAction.value = null
  if (!response?.ok) {
    logger.warn('token_mutation_failed', { kind: action.kind, status: response?.status })
    toast.error(`Token ${action.kind} failed. Nothing was changed.`)
    return
  }
  if (action.kind === 'rotate') {
    copied.value = false
    showMinted(data)
  } else {
    toast.success('Token revoked. Its next push will be rejected')
  }
  await load()
}

const fmt = (iso: string | null) =>
  iso === null
    ? '-'
    : new Date(iso).toLocaleString('en-GB', { hour12: false, dateStyle: 'medium', timeStyle: 'short' })
</script>

<template>
  <div class="stack">
    <SettingsCard
      title="Access & tokens"
      subtitle="one scoped push token per (cluster, scanner). HTTPS ingest is the only credential surface"
    >
      <template #action>
        <UiButton :disabled="busy" @click="openMint"><AppIcon name="plus" :size="13" />Mint token</UiButton>
      </template>

      <UiSkeleton
        v-if="loading"
        :height="120"
        radius="sm"
        label="Loading tokens"
        class="skel-gap"
      />
      <p v-else-if="failed" class="load-error" role="alert">
        Token list unavailable. Check the backend connection.
      </p>
      <p v-else-if="rows.length === 0" class="empty-note" role="status">
        No push tokens yet. Mint one per scanner so the cluster can start pushing scans.
      </p>
      <p v-else-if="total > rows.length" class="cap-note">
        Showing the {{ rows.length }} newest of {{ total }} tokens.
      </p>

      <div v-if="!loading && !failed && rows.length" class="set-flush">
      <div class="tbl-wrap">
        <table class="tbl tbl-dense tbl-quiet tbl-hover">
          <thead>
            <tr>
              <th class="fit">Scanner</th>
              <th>Cluster</th>
              <th class="fit">Scope</th>
              <th class="fit">Created</th>
              <th class="fit">Expiry</th>
              <th class="fit">Last used</th>
              <th class="fit">Status</th>
              <th class="fit"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in shown" :key="row.id">
              <td class="fit"><ScannerTag :name="row.scanner" /></td>
              <td>
                <span class="mono-cell sm cluster-cell" :title="row.cluster_id">{{
                  clusterName(row.cluster_id)
                }}</span>
              </td>
              <td class="fit mono-cell sm"><template v-if="row.scope != null">{{ row.scope }}</template><span v-else class="muted-dash">-</span></td>
              <td class="fit mono-cell sm nowrap" :title="row.created_at ?? undefined">{{ fmt(row.created_at) }}</td>
              <td class="fit mono-cell sm nowrap">{{ row.expiry === null ? 'never' : fmt(row.expiry) }}</td>
              <td class="fit mono-cell sm nowrap">{{ fmt(row.last_ingest_at) }}</td>
              <td class="fit"><DotWord :tone="TOKEN_STATUS_TONE[tokenStatus(row, now())]" :label="tokenStatus(row, now())" /></td>
              <td class="fit">
                <span v-if="tokenStatus(row, now()) !== 'revoked'" class="row-actions">
                  <!-- the new token takes the old expiry: an expired one is replaced by a mint (issue 984) -->
                  <UiButton
                    v-if="tokenStatus(row, now()) === 'active'"
                    :disabled="busy"
                    @click="confirmAction = { kind: 'rotate', row }"
                  >Rotate</UiButton>
                  <UiButton :disabled="busy" @click="confirmAction = { kind: 'revoke', row }">Revoke</UiButton>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <GridPager
          :total="rows.length"
          :page="page"
          :size="size"
          :shown="shown.length"
          :has-prev="page > 0"
          :has-next="hasNext"
          @prev="page -= 1"
          @next="page += 1"
          @update:size="setSize"
        />
      </div>
      </div>
    </SettingsCard>

    <!-- mint dialog -->
    <ModalShell v-if="mintOpen" title="Mint a push token" subtitle="scoped to one (cluster, scanner) pair" @close="mintOpen = false">
      <UiField label="Cluster" first for="mint-cluster">
        <select id="mint-cluster" v-model="mintCluster" class="set-select">
          <option v-for="c in activeClusters" :key="c.cluster_id" :value="c.cluster_id">
            {{ c.cluster_name }}
          </option>
          <option :value="NEW_CLUSTER">New cluster…</option>
          <optgroup v-if="retiredClusters.length" label="Retired">
            <option v-for="c in retiredClusters" :key="c.cluster_id" :value="c.cluster_id">
              {{ c.cluster_name }} (retired)
            </option>
          </optgroup>
        </select>
      </UiField>
      <p v-if="mintRetired" class="fld-hint" role="status">
        {{ mintRetired.cluster_name }} is retired. Its first scan on this token brings it back to the cluster
        list.
      </p>
      <UiField
        v-if="mintCluster === NEW_CLUSTER"
        label="Cluster ID"
        hint="the UID of its kube-system namespace"
        for="mint-cluster-id"
      >
        <SettingsInput id="mint-cluster-id" v-model="mintNewId" :invalid="mintIdProblem !== null" />
        <p v-if="mintIdProblem" class="modal-error" role="alert">{{ mintIdProblem }}</p>
        <p class="fld-hint">Run this in the cluster to print it:</p>
        <div class="raw-token mono-cell sm cmd">{{ CLUSTER_ID_COMMAND }}</div>
      </UiField>
      <UiField label="Scanner" hint="per-scanner is sacred: one token each">
        <UiSegControl v-model="mintScanner" :options="SCANNER_OPTS" />
      </UiField>
      <UiField label="Expiry" hint="optional: must be in the future; ingest rejects the token past it">
        <UiDateTime v-model="mintExpiryParts" id-prefix="mint-expiry" :invalid="mintExpiryInvalid" />
      </UiField>
      <p class="fld-hint">Leave both fields empty for a non-expiring token. Time is 24h, your local zone.</p>
      <p v-if="mintError" class="modal-error" role="alert">{{ mintError }}</p>
      <template #actions>
        <UiButton variant="ghost" @click="mintOpen = false">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy || mintTarget === null || mintExpiryInvalid" @click="submitMint">
          {{ busy ? 'Minting…' : 'Mint token' }}
        </UiButton>
      </template>
    </ModalShell>

    <!-- the raw-token-once modal -->
    <ModalShell
      v-if="minted"
      title="Copy this token now"
      subtitle="it is shown once and cannot be recovered: a lost token is a rotate"
      @close="minted = null"
    >
      <div class="raw-token mono-cell sm">{{ minted.token }}</div>
      <template #actions>
        <UiButton variant="primary" @click="copyToken">{{ copied ? 'Copied ✓' : 'Copy token' }}</UiButton>
        <UiButton variant="ghost" @click="minted = null">Done</UiButton>
      </template>
    </ModalShell>

    <!-- rotate/revoke confirm -->
    <ModalShell
      v-if="confirmAction"
      :title="confirmAction.kind === 'rotate' ? 'Rotate this token?' : 'Revoke this token?'"
      @close="confirmAction = null"
    >
      <p class="confirm-copy">
        <template v-if="confirmAction.kind === 'rotate'">
          A replacement is minted first (inheriting the expiry), then this token is disabled,
          so the scanner is never token-less. You'll get the new raw token once.
        </template>
        <template v-else>
          The scanner's next push with this token will be rejected. Revocation is journaled and
          cannot be undone. A revoked token stays listed for the audit trail.
        </template>
      </p>
      <template #actions>
        <UiButton variant="ghost" @click="confirmAction = null">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy" @click="runConfirmed">
          {{ busy ? 'Working…' : confirmAction.kind === 'rotate' ? 'Rotate' : 'Revoke' }}
        </UiButton>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.cluster-cell {
  display: block;
  max-width: 0;
  min-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-actions {
  display: inline-flex;
  gap: 6px;
}
.raw-token {
  padding: 12px 14px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  word-break: break-all;
  user-select: all;
}
.set-select {
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  padding: 8px 11px;
  font-size: var(--text-body);
  font-family: var(--font-ui);
  color: var(--ink);
  background: var(--card);
  width: 100%;
}
.set-select:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.set-select:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.fld-hint {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
/* the command to copy: the raw-token block, tighter, under its hint, on one line at the dialog's
   width (the token's break-all would split it mid-word) */
.raw-token.cmd {
  margin-top: 4px;
  padding: 7px 10px;
  font-size: var(--text-sm);
  word-break: normal;
  overflow-wrap: anywhere;
}
.empty-note,
.cap-note {
  margin: 14px 0 8px;
  color: var(--soft);
}
.cap-note {
  font-size: var(--text-sm);
}
.load-error {
  margin: 14px 0 8px;
}
.skel-gap {
  margin: 14px 0 8px;
}
</style>

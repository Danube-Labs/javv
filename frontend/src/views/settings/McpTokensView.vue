<script setup lang="ts">
/**
 * AI agents (MCP), SCREENS §13.9 (issue 1096 step 4): the can_manage_tokens section for MCP tokens.
 * It is built on the parts of Access & tokens (§13.5): the token list is one server answer shown a
 * page at a time, and a new token shows one time in the shared window. Two things differ from a
 * scanner token: an MCP token always has an expiry, 90 days at most, and a rotate stops the old
 * secret at once and needs a new expiry, so the Rotate window asks for one.
 */
import { computed, ref } from 'vue'

import {
  getMetaApiV1MetaGet,
  listTokensApiV1AdminMcpTokensGet,
  makeApiV1AdminMcpTokensPost,
  revokeApiV1AdminMcpTokensNameRevokePost,
  rotateApiV1AdminMcpTokensNameRotatePost,
} from '@/api/generated'
import { client } from '@/api/client'
import DotWord from '@/components/chips/DotWord.vue'
import GridPager from '@/components/findings/GridPager.vue'
import CopyValue from '@/components/settings/CopyValue.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import TokenOnceDialog from '@/components/settings/TokenOnceDialog.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import UiTextBox from '@/components/ui/UiTextBox.vue'
import { readFailureCopy } from '@/findings/failureCopy'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

import {
  defaultExpiryDay,
  endpointUrl,
  EXPIRY_HINT,
  EXPIRY_PROBLEM,
  expiryIso,
  expiryRange,
  levelLabel,
  MCP_LEVELS,
  MCP_NAME,
  MCP_NAME_HINT,
  type McpLevel,
  type McpTokenRow,
} from './mcpTokensForm'
import { TOKEN_STATUS_TONE, tokenStatus } from './tokensForm'

const toast = useToastStore()

// ── the endpoint ───────────────────────────────────────────────────────────────────────────
const enabled = ref<boolean | null>(null) // null: not read yet, or the read failed
const metaFailed = ref(false)
const url = endpointUrl(window.location.origin)

async function loadMeta() {
  const { data, response } = await getMetaApiV1MetaGet({ client })
  metaFailed.value = !response?.ok || !data
  if (metaFailed.value) {
    logger.warn('mcp_meta_failed', { status: response?.status })
    return
  }
  enabled.value = (data as { mcp_enabled?: boolean }).mcp_enabled === true
}
void loadMeta()

// ── the tokens ─────────────────────────────────────────────────────────────────────────────
const rows = ref<McpTokenRow[]>([])
const total = ref(0)
const loading = ref(true)
const failed = ref<string | null>(null)
const busy = ref(false)

const LIST_SIZE = 100 // the route's default page: one page holds the tokens of a team

async function load() {
  loading.value = true
  const { data, response } = await listTokensApiV1AdminMcpTokensGet({ client, query: { size: LIST_SIZE } })
  loading.value = false
  failed.value =
    response?.ok && data
      ? null
      : readFailureCopy(response?.status ?? null, 'The token list is not available. Check the backend connection.')
  if (failed.value !== null) {
    logger.warn('mcp_tokens_load_failed', { status: response?.status })
    return
  }
  const body = data as { tokens: McpTokenRow[]; total: number }
  rows.value = body.tokens
  total.value = body.total
}
void load()

const now = () => new Date()

const page = ref(0)
const size = ref(10)
const shown = computed(() => rows.value.slice(page.value * size.value, (page.value + 1) * size.value))
const hasNext = computed(() => (page.value + 1) * size.value < rows.value.length)
function setSize(next: number) {
  size.value = next
  page.value = 0
}

const fmt = (iso: string | null) =>
  iso === null ? '-' : new Date(iso).toLocaleString('en-GB', { hour12: false, dateStyle: 'medium', timeStyle: 'short' })
// an expiry is 00:00 UTC of its day, so the day is read in UTC: a local zone would show the day before
const fmtDay = (iso: string | null) =>
  iso === null ? '-' : new Date(iso).toLocaleDateString('en-GB', { dateStyle: 'medium', timeZone: 'UTC' })

// a new token shows one time, after a make or a rotate
const shownToken = ref<string | null>(null)

function showToken(data: unknown) {
  const token = (data as { token?: string } | undefined)?.token
  if (token) {
    shownToken.value = token
    return
  }
  // the token exists once the reply is OK, but its value comes only in the body
  logger.warn('mcp_token_value_lost')
  toast.error('The token was made, but its value did not reach this page. Rotate it to get a value you can copy.')
}

// ── make ───────────────────────────────────────────────────────────────────────────────────
const makeOpen = ref(false)
const makeName = ref('')
const makeLevel = ref<McpLevel>('read')
const makeDay = ref('')
const makeError = ref('')
const range = ref(expiryRange(Date.now()))

const nameProblem = computed(() =>
  makeName.value !== '' && !MCP_NAME.test(makeName.value) ? `A name has ${MCP_NAME_HINT}.` : null,
)
const makeExpiry = computed(() => expiryIso(makeDay.value, Date.now()))
const levelNote = computed(() => MCP_LEVELS.find((l) => l.value === makeLevel.value)?.note ?? '')

function openMake() {
  makeName.value = ''
  makeLevel.value = 'read'
  range.value = expiryRange(Date.now())
  makeDay.value = defaultExpiryDay(Date.now())
  makeError.value = ''
  makeOpen.value = true
}

async function submitMake() {
  const expiry = makeExpiry.value
  if (!MCP_NAME.test(makeName.value) || expiry === null) return
  busy.value = true
  const { data, response } = await makeApiV1AdminMcpTokensPost({
    client,
    body: { name: makeName.value, level: makeLevel.value, expiry },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('mcp_token_make_failed', { status: response?.status })
    makeError.value =
      response?.status === 409
        ? 'A token with this name exists. Choose another name.'
        : response?.status === 403
          ? 'Making a token needs the can_manage_tokens permission.'
          : 'The token was not made.'
    return
  }
  makeOpen.value = false
  showToken(data)
  await load()
}

// ── rotate and revoke ──────────────────────────────────────────────────────────────────────
const rotateRow = ref<McpTokenRow | null>(null)
const rotateDay = ref('')
const rotateExpiry = computed(() => expiryIso(rotateDay.value, Date.now()))
const revokeRow = ref<McpTokenRow | null>(null)

function openRotate(row: McpTokenRow) {
  range.value = expiryRange(Date.now())
  rotateDay.value = defaultExpiryDay(Date.now())
  rotateRow.value = row
}

async function submitRotate() {
  const row = rotateRow.value
  const expiry = rotateExpiry.value
  if (row === null || expiry === null) return
  busy.value = true
  const { data, response } = await rotateApiV1AdminMcpTokensNameRotatePost({
    client,
    path: { name: row.name },
    body: { expiry },
  })
  busy.value = false
  rotateRow.value = null
  if (!response?.ok) {
    logger.warn('mcp_token_rotate_failed', { status: response?.status })
    toast.error(
      response?.status === 409
        ? 'The token is revoked or has expired. Make a new token.'
        : 'The rotate failed. The old token still works.',
    )
    await load()
    return
  }
  showToken(data)
  await load()
}

async function submitRevoke() {
  const row = revokeRow.value
  if (row === null) return
  busy.value = true
  const { response } = await revokeApiV1AdminMcpTokensNameRevokePost({ client, path: { name: row.name } })
  busy.value = false
  revokeRow.value = null
  if (!response?.ok) {
    logger.warn('mcp_token_revoke_failed', { status: response?.status })
    toast.error('The revoke failed. The token still works.')
    return
  }
  toast.success(`Token ${row.name} revoked. The agent that uses it is refused from now on.`)
  await load()
}
</script>

<template>
  <div class="stack">
    <SettingsCard title="Endpoint" subtitle="where an AI agent connects to JAVV">
      <SettingsRow
        label="Status"
        :hint="
          enabled === false
            ? 'To turn it on, set JAVV_MCP_ENABLED to true on the backend and start the backend again.'
            : 'An agent sends its MCP token in the Authorization header.'
        "
      >
        <UiSkeleton v-if="enabled === null && !metaFailed" :height="20" radius="sm" label="Loading the status" />
        <DotWord v-else-if="metaFailed" tone="warn" label="unknown: the status could not be read" />
        <DotWord v-else :tone="enabled ? 'ok' : 'muted'" :label="enabled ? 'on' : 'off'" />
      </SettingsRow>
      <SettingsRow label="URL" hint="The address of this page, plus /api/v1/mcp." stack>
        <CopyValue :value="url" copy="Copy the URL" />
      </SettingsRow>
    </SettingsCard>

    <SettingsCard title="Tokens" subtitle="one token for each AI agent, with a level and an expiry">
      <template #action>
        <UiButton :disabled="busy" @click="openMake"><AppIcon name="plus" :size="13" />Make token</UiButton>
      </template>

      <UiSkeleton v-if="loading" :height="120" radius="sm" label="Loading tokens" class="skel-gap" />
      <p v-else-if="failed" class="load-error" role="alert">{{ failed }}</p>
      <p v-else-if="rows.length === 0" class="empty-note" role="status">
        No MCP tokens yet. Make one for each AI agent that connects.
      </p>
      <p v-else-if="total > rows.length" class="cap-note">
        Showing the {{ rows.length }} newest of {{ total }} tokens.
      </p>

      <div v-if="!loading && !failed && rows.length" class="set-flush">
        <div class="tbl-wrap">
          <!-- the columns outgrow the card at the 1024 floor: the table scrolls, the name stays -->
          <div class="tbl-scroll-pin">
          <table class="tbl tbl-dense tbl-quiet tbl-hover">
            <thead>
              <tr>
                <th>Name</th>
                <th class="fit">Level</th>
                <th class="fit">Created by</th>
                <th class="fit">Created</th>
                <th class="fit">Expiry</th>
                <th class="fit">Last used</th>
                <th class="fit">Status</th>
                <th class="fit"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in shown" :key="row.name">
                <td class="mono-cell sm nowrap">{{ row.name }}</td>
                <td class="fit nowrap">{{ levelLabel(row.level) }}</td>
                <td class="fit mono-cell sm">{{ row.created_by ?? '-' }}</td>
                <td class="fit mono-cell sm nowrap" :title="row.created_at ?? undefined">{{ fmt(row.created_at) }}</td>
                <td class="fit mono-cell sm nowrap" :title="row.expiry ?? undefined">{{ fmtDay(row.expiry) }}</td>
                <td class="fit mono-cell sm nowrap">{{ row.last_used_at === null ? 'never' : fmt(row.last_used_at) }}</td>
                <td class="fit">
                  <DotWord :tone="TOKEN_STATUS_TONE[tokenStatus(row, now())]" :label="tokenStatus(row, now())" />
                </td>
                <td class="fit">
                  <span v-if="tokenStatus(row, now()) !== 'revoked'" class="row-actions">
                    <!-- the backend refuses to rotate an expired token: it gets a new token instead -->
                    <UiButton v-if="tokenStatus(row, now()) === 'active'" :disabled="busy" @click="openRotate(row)">
                      Rotate
                    </UiButton>
                    <UiButton :disabled="busy" @click="revokeRow = row">Revoke</UiButton>
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
          </div>
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

    <ModalShell v-if="makeOpen" title="Make an MCP token" subtitle="for one AI agent" @close="makeOpen = false">
      <UiField label="Name" first :hint="MCP_NAME_HINT" for="mcp-name">
        <UiTextBox id="mcp-name" v-model="makeName" :invalid="nameProblem !== null" />
      </UiField>
      <p v-if="nameProblem" class="modal-error" role="alert">{{ nameProblem }}</p>
      <p class="fld-hint">The Audit log names the agent mcp:{{ makeName || 'name' }}.</p>
      <UiField label="Level">
        <UiSegControl v-model="makeLevel" :options="MCP_LEVELS" label="Level" />
      </UiField>
      <p class="fld-hint" role="status">{{ levelNote }}</p>
      <UiField label="Expiry" :hint="EXPIRY_HINT" for="mcp-expiry">
        <UiTextBox
          id="mcp-expiry"
          v-model="makeDay"
          type="date"
          :min="range.first"
          :max="range.last"
          :invalid="makeExpiry === null"
        />
      </UiField>
      <p v-if="makeExpiry === null" class="modal-error" role="alert">{{ EXPIRY_PROBLEM }}</p>
      <p v-if="makeError" class="modal-error" role="alert">{{ makeError }}</p>
      <template #actions>
        <UiButton variant="ghost" @click="makeOpen = false">Cancel</UiButton>
        <UiButton
          variant="primary"
          :disabled="busy || !MCP_NAME.test(makeName) || makeExpiry === null"
          @click="submitMake"
        >
          {{ busy ? 'Making…' : 'Make token' }}
        </UiButton>
      </template>
    </ModalShell>

    <ModalShell
      v-if="rotateRow"
      :title="`Rotate ${rotateRow.name}?`"
      subtitle="a new token with a new expiry"
      @close="rotateRow = null"
    >
      <p class="confirm-copy">
        The old token stops at once. The agent is refused until you give it the new token, which you
        see one time. The name and the level stay.
      </p>
      <UiField label="New expiry" :hint="EXPIRY_HINT" for="mcp-rotate-expiry">
        <UiTextBox
          id="mcp-rotate-expiry"
          v-model="rotateDay"
          type="date"
          :min="range.first"
          :max="range.last"
          :invalid="rotateExpiry === null"
        />
      </UiField>
      <p v-if="rotateExpiry === null" class="modal-error" role="alert">{{ EXPIRY_PROBLEM }}</p>
      <template #actions>
        <UiButton variant="ghost" @click="rotateRow = null">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy || rotateExpiry === null" @click="submitRotate">
          {{ busy ? 'Working…' : 'Rotate' }}
        </UiButton>
      </template>
    </ModalShell>

    <ModalShell v-if="revokeRow" title="Revoke this token?" @close="revokeRow = null">
      <p class="confirm-copy">
        The agent that uses {{ revokeRow.name }} is refused from now on. A revoke cannot be undone. The
        token stays in the list for the Audit log.
      </p>
      <template #actions>
        <UiButton variant="ghost" @click="revokeRow = null">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy" @click="submitRevoke">{{ busy ? 'Working…' : 'Revoke' }}</UiButton>
      </template>
    </ModalShell>

    <TokenOnceDialog
      v-if="shownToken"
      :token="shownToken"
      subtitle="it is shown one time and cannot be recovered: a lost token is a rotate"
      @close="shownToken = null"
    />
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.row-actions {
  display: inline-flex;
  gap: 6px;
}
.fld-hint {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.empty-note,
.cap-note {
  margin: 14px 0 8px;
  color: var(--soft);
}
.cap-note {
  font-size: var(--text-sm);
}
.load-error,
.skel-gap {
  margin: 14px 0 8px;
}
</style>

<script setup lang="ts">
/**
 * Data inspector (issue 406 — the shipped mockup's console + rail): raw read-only queries
 * through the backend's allowlist proxy. Left rail = INDEX-MAP-grouped indices from
 * `_cat/indices`; main = request editor + response pane with the byte-budget meter; every
 * rejection renders the backend's reason verbatim. The mockup's repair-actions card sits below
 * the console (`RepairActionsCard`) — the three sanctioned, journaled jobs, lifecycle behind a
 * confirm. Both loops are covered at the browser seam by `tests/e2e/inspect.spec.ts`.
 */
import { computed, onMounted, ref } from 'vue'

import { client } from '@/api/client'
import { inspectStoreApiV1AdminOpensearchInspectPost } from '@/api/generated'
import InspectHeadFacts from '@/components/system/InspectHeadFacts.vue'
import InspectRail from '@/components/system/InspectRail.vue'
import RepairActionsCard from '@/components/system/RepairActionsCard.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiTextBox from '@/components/ui/UiTextBox.vue'
import { logger } from '@/lib/logger'
import {
  fmtBytes,
  groupIndices,
  totalStoreBytes,
  type CatIndexRow,
  type RailGroups,
} from '@/system/inspect'

const METHODS = [
  { value: 'GET', label: 'GET' },
  { value: 'POST', label: 'POST' },
] as const

/* ---- console state ---- */
const method = ref<'GET' | 'POST'>('POST')
const path = ref('findings/_search')
const bodyText = ref('{\n  "size": 3,\n  "query": { "match_all": {} }\n}')
const running = ref(false)
const tookMs = ref<number | null>(null)
const bytes = ref(0)
const capBytes = ref(0)
const responseText = ref('')
const errorText = ref('')

/* ---- rail + head stats ---- */
const rail = ref<RailGroups>({ history: [], state: [], system: [] })
const indexCount = ref<number | null>(null)
const storeBytes = ref(0)
const health = ref('')
const railFailed = ref(false)

async function proxy(m: 'GET' | 'POST', p: string, b?: unknown) {
  return inspectStoreApiV1AdminOpensearchInspectPost({
    client,
    body: { method: m, path: p, body: (b ?? null) as Record<string, unknown> | null },
  })
}

onMounted(async () => {
  const [indices, clusterHealth] = await Promise.all([
    proxy('GET', '_cat/indices'),
    proxy('GET', '_cluster/health'),
  ])
  if (indices.response?.ok && indices.data) {
    const rows = (indices.data as { body: CatIndexRow[] }).body
    rail.value = groupIndices(rows)
    indexCount.value = rows.length
    storeBytes.value = totalStoreBytes(rows)
  } else {
    railFailed.value = true
  }
  if (clusterHealth.response?.ok && clusterHealth.data) {
    health.value = (clusterHealth.data as { body: { status?: string } }).body.status ?? ''
  }
})

function pickIndex(pattern: string) {
  path.value = `${pattern}/_search`
  method.value = 'POST'
}

const activePattern = computed(() => path.value.split('/')[0] ?? '')

function pretty() {
  try {
    bodyText.value = JSON.stringify(JSON.parse(bodyText.value), null, 2)
    errorText.value = ''
  } catch (e) {
    errorText.value = `Body is not valid JSON: ${(e as Error).message}`
  }
}

async function run() {
  if (running.value) return
  errorText.value = ''
  let body: unknown
  if (bodyText.value.trim() && method.value === 'POST') {
    try {
      body = JSON.parse(bodyText.value)
    } catch (e) {
      errorText.value = `Body is not valid JSON: ${(e as Error).message}`
      return
    }
  }
  running.value = true
  try {
    const r = await proxy(method.value, path.value, body)
    if (r.response?.ok && r.data) {
      const out = r.data as {
        took_ms: number
        bytes: number
        cap_bytes: number
        body: unknown
      }
      tookMs.value = out.took_ms
      bytes.value = out.bytes
      capBytes.value = out.cap_bytes
      responseText.value = JSON.stringify(out.body, null, 2)
      logger.info('inspect_query', { path: path.value, took_ms: out.took_ms, bytes: out.bytes })
    } else {
      // the backend's rejection reason, verbatim (problem+json carries it in `title`)
      const problem = (r.error ?? null) as { title?: string } | null
      errorText.value = `${r.response?.status ?? '?'}: ${problem?.title ?? 'request failed'}`
      logger.warn('inspect_rejected', { path: path.value, status: r.response?.status })
    }
  } finally {
    running.value = false
  }
}

function onEditorKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    void run()
  }
}

const budgetPct = computed(() =>
  capBytes.value ? Math.min(100, Math.round((bytes.value / capBytes.value) * 100)) : 0,
)
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card head-card-fluid">
        <h1>Data inspector</h1>
        <p class="screen-sub">
          Raw read-only queries against the OpenSearch store: verify mappings, debug ingest,
          answer "what is actually in the index". Every query is journaled. Spans
          <b>all clusters</b>. The topbar cluster picker does not scope this console; filter
          on <code>cluster_id</code> in the query itself.
        </p>
      </div>
      <InspectHeadFacts :index-count="indexCount" :store-bytes="storeBytes" :health="health" />
    </div>

    <div class="inspect-cols">
      <InspectRail
        :groups="rail"
        :active-pattern="activePattern"
        :failed="railFailed"
        @pick="pickIndex"
      />

      <section class="card console">
        <h2 class="panel-band">Query</h2>
        <div class="console-head">
          <UiSegControl v-model="method" :options="METHODS" label="HTTP method" />
          <UiTextBox
            v-model="path"
            class="pathbox"
            spellcheck="false"
            aria-label="Store path"
            placeholder="findings/_search · _cat/indices · _cluster/health"
            @keydown="onEditorKeydown"
          />
          <UiButton variant="control" @click="pretty">Pretty</UiButton>
          <UiButton variant="primary" :disabled="running" @click="run">
            <AppIcon name="pulse" :size="13" />Run ⌘↵
          </UiButton>
        </div>
        <div class="runbar" :class="{ live: running }" aria-hidden="true" />

        <div class="split">
          <div class="pane">
            <div class="pane-label">
              Request body <span class="quiet">JSON · ⌘↵ runs</span>
            </div>
            <!-- eslint-disable-next-line vue/no-restricted-html-elements -- the request body is a code panel, not a form field -->
            <textarea
              v-model="bodyText"
              class="editor"
              spellcheck="false"
              aria-label="Request body JSON"
              :disabled="method === 'GET'"
              @keydown="onEditorKeydown"
            />
            <p v-if="errorText" class="reject" role="alert">
              <b>{{ errorText.split(': ')[0] }}</b>
              <span>{{ errorText.split(': ').slice(1).join(': ') }}</span>
            </p>
          </div>
          <div class="pane">
            <div class="pane-label">
              Response
              <span v-if="tookMs !== null" class="quiet">took {{ tookMs }} ms</span>
            </div>
            <pre v-if="responseText" class="response">{{ responseText }}</pre>
            <p v-else class="response-empty">Run a query. The untransformed store response lands here.</p>
            <div v-if="capBytes" class="budget">
              <div class="budget-row">
                <span>response budget</span>
                <span>{{ fmtBytes(bytes) }} / {{ fmtBytes(capBytes) }} cap</span>
              </div>
              <div class="budget-track"><div class="budget-fill" :style="{ width: `${budgetPct}%` }" /></div>
            </div>
          </div>
        </div>

        <p class="journal-note">
          <b>recorded</b> Every query you run here lands in the audit log: who ran it, against
          what, and when. Nothing on this page is anonymous.
        </p>
      </section>
    </div>

    <RepairActionsCard />
  </div>
</template>

<style scoped>
/* the description gives way to the facts at any width, so long values (a four-digit index count,
   "1023.9 GB") wrap it instead of running off the screen. Below 1340px even short facts no
   longer fit in a row beside it, so they stack in a column (issue 652) */
.screen-head-band > .head-card {
  flex: 0 1 auto;
  min-width: 0;
}
@media (width < 1340px) {
  .screen-head-band > .head-facts {
    flex-direction: column;
    gap: 4px;
    padding: 10px 16px;
  }
}
.inspect-cols {
  display: grid;
  grid-template-columns: var(--facet-rail-w) 1fr;
  gap: var(--grid-gap);
  align-items: start;
}
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
}

/* ---- console ---- */
/* the B2 slate table-head band as both cards' title register (operator, 2026-07-18) */
.panel-band {
  margin: 0;
  padding: 10px 16px;
  background: var(--table-head-bg);
  color: var(--table-head-fg);
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.console {
  overflow: hidden;
}
.console-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
}
.pathbox {
  flex: 1;
  min-width: 0;
}

/* the in-flight indicator (mockup: framework7 infinite bar) — 3px under the toolbar */
.runbar {
  height: 3px;
  background: var(--line2);
  overflow: hidden;
  position: relative;
}
.runbar.live::after {
  content: '';
  position: absolute;
  inset: 0;
  width: 38%;
  background: var(--coral);
  border-radius: 2px;
  animation: inspect-sweep 1.1s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
@keyframes inspect-sweep {
  from {
    transform: translateX(-110%);
  }
  to {
    transform: translateX(300%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .runbar.live::after {
    animation: none;
    width: 100%;
    opacity: 0.45;
  }
}

/* the console owns the viewport (operator, 2026-07-18: no need to keep it short) — panes
   fill the height left under the topbar/head band instead of a fixed strip */
.split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  min-height: max(440px, calc(100vh - 420px));
}
.pane {
  padding: 12px 16px 16px;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.pane + .pane {
  border-left: 1px solid var(--line2);
}
.pane-label {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--soft);
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}
.pane-label .quiet {
  text-transform: none;
  letter-spacing: 0;
  font-size: var(--text-sm);
}
.editor,
.response {
  flex: 1;
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--text-mono-cell);
  line-height: 1.55;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: var(--r-sm);
  padding: 12px 14px;
  tab-size: 2;
}
.editor {
  resize: vertical;
  min-height: 340px;
  color: var(--ink);
}
.editor:hover {
  border-color: var(--control-hover-line);
}
.editor:focus-visible {
  outline: 2px solid var(--coral);
  outline-offset: 1px;
}
.editor:disabled {
  opacity: 0.55;
}
.response {
  overflow: auto;
  max-height: calc(100vh - 460px);
  white-space: pre;
}
.response-empty {
  flex: 1;
  display: grid;
  place-items: center;
  margin: 0;
  color: var(--soft);
  font-size: var(--text-body);
  background: var(--panel);
  border: 1px dashed var(--line);
  border-radius: var(--r-sm);
}

.reject {
  margin: 12px 0 0;
  display: flex;
  gap: 10px;
  align-items: baseline;
  background: var(--sev-critical-bg);
  border: 1px solid var(--sev-critical-line);
  border-radius: var(--r-sm);
  padding: 9px 13px;
  font-size: var(--text-control);
}
.reject b {
  font-family: var(--font-mono);
  font-size: var(--text-chip);
  color: var(--sev-critical-fg);
  flex: none;
}

.budget {
  margin-top: 10px;
}
.budget-row {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--soft);
  margin-bottom: 4px;
}
.budget-track {
  height: 5px;
  border-radius: 3px;
  background: var(--line2);
  overflow: hidden;
}
.budget-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--teal);
}

.journal-note {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin: 0;
  padding: 10px 16px;
  border-top: 1px solid var(--line2);
  color: var(--soft);
  font-size: var(--text-body);
}
.journal-note b {
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--teal-text);
}
</style>

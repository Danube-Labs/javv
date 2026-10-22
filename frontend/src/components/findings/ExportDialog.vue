<script setup lang="ts">
/**
 * Export the current lens (M9b slice 4, C-2 states; lens fidelity + past-T per audit
 * F-07/F-08). Run-now streams inline (413 past JAVV_EXPORT_MAX_ROWS → offer the schedule
 * path); Schedule enqueues an off-peak report and polls to the signed download link with its
 * expiry. VEX is per-scanner by contract (one scanner per file — per-scanner sacred).
 * Scheduling carries the COMPLETE lens (every ExportParams field); a lens key the contract
 * can't represent BLOCKS scheduling loudly rather than silently widening the export. At
 * T<now run-now stays off (inline streams describe current state) but Schedule sends
 * `as_of_t` — the drain reconstructs the rows as-scanned at T (M8b).
 */
import { computed, onUnmounted, ref } from 'vue'

import { enqueueReportApiV1ReportsPost, getReportApiV1ReportsReportIdGet } from '@/api/generated'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { useApi } from '@/composables/useApi'
import { useCsvExport } from '@/composables/useCsvExport'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { exportBlockMessage, scheduleParams } from '@/findings/exportParams'
import type { FilterField } from '@/filters/fields.config'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{
  fields: readonly FilterField[]
  selections: Record<string, string[]>
  modes?: Record<string, 'is' | 'not'>
  historical: boolean
}>()
const clusterStore = useClusterStore()
const toast = useToastStore()
const { withGlobals } = useApi()

const open = ref(false)
const tab = ref<'now' | 'schedule'>('now')
const format = ref<'csv' | 'vex'>('csv')
const vexScanner = ref<'trivy' | 'grype'>('trivy')
const TAB_OPTS = [
  { value: 'now', label: 'Run now' },
  { value: 'schedule', label: 'Schedule off-peak' },
] as const
const FORMAT_OPTS = [
  { value: 'csv', label: 'CSV' },
  { value: 'vex', label: 'VEX (OpenVEX)' },
] as const
const SCANNER_OPTS = [
  { value: 'trivy', label: 'trivy' },
  { value: 'grype', label: 'grype' },
] as const
const busy = ref(false)
const error = ref<string | null>(null)
const report = ref<{ id: string; status: string; token?: string; expires_at?: string } | null>(null)
let poll: ReturnType<typeof setInterval> | null = null

const timeTravel = useTimeTravelStore()
const lensQuery = computed(() =>
  buildFilterQuery(
    props.fields,
    props.selections,
    { ...withGlobals(), window_days: timeTravel.windowDays },
    props.modes ?? {},
  ),
)
/** An export the backend would refuse, or one with other rows than the screen, is BLOCKED on
 * either tab — never silently widened past what's on screen (audit F-07, issue 962). */
const blocked = computed(() =>
  exportBlockMessage(props.fields, lensQuery.value, {
    schedule: tab.value === 'schedule',
    historical: props.historical,
    format: format.value,
    vexScanner: vexScanner.value,
  }),
)

function openDialog() {
  error.value = null
  report.value = null
  // at a past T only the queued path exists — inline streams describe current state
  tab.value = props.historical ? 'schedule' : 'now'
  // a VEX file speaks for the scanner the screen shows, when it shows one
  const shown = lensQuery.value.scanner
  if (shown === 'trivy' || shown === 'grype') vexScanner.value = shown
  open.value = true
}
function close() {
  open.value = false
  if (poll) clearInterval(poll)
  poll = null
}
onUnmounted(() => {
  if (poll) clearInterval(poll)
})

/* ---- run now: useCsvExport owns fetch → blob → download (so 413/501 surface as messages,
 * not broken tabs); this dialog's 413 pivots to the schedule tab instead of toasting ---- */
const { exporting, run: runExport } = useCsvExport({
  path: () => `/api/v1/findings/${format.value === 'csv' ? 'export.csv' : 'export.vex'}`,
  filename: (stamp) => `javv-findings-${stamp}.${format.value === 'csv' ? 'csv' : 'openvex.json'}`,
  event: 'export_failed',
  onCapped: () => {
    error.value = 'Too many rows for a direct export. Narrow the filters, or schedule it for a quiet time.'
    tab.value = 'schedule'
  },
  onFailed: (status) => {
    error.value = status
      ? `Export failed (${status}). Check the backend connection.`
      : 'Export failed. Check the backend connection.'
  },
  onDone: (name) => {
    logger.info('export_downloaded', { format: format.value })
    toast.success(`Export downloaded · ${name}`)
  },
})

async function runNow() {
  error.value = null
  const q = { ...lensQuery.value } as Record<string, unknown>
  if (format.value === 'vex') q.scanner = vexScanner.value
  await runExport(q)
}

/* ---- schedule: enqueue → poll status → signed download link + expiry ---- */
function expiresIn(iso?: string): string {
  if (!iso) return ''
  const h = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000))
  return `expires in ~${h}h`
}
async function schedule() {
  busy.value = true
  error.value = null
  const params = scheduleParams(lensQuery.value, format.value, vexScanner.value)
  const response = await enqueueReportApiV1ReportsPost({
    body: {
      kind: 'export',
      cluster_id: clusterStore.selectedId!,
      run_mode: 'offpeak',
      params,
      // a rewound lens exports AT T — the drain reconstructs as-scanned rows (F-08)
      ...(timeTravel.t !== null ? { as_of_t: timeTravel.t } : {}),
    } as never,
  })
  busy.value = false
  if (response.response?.ok && response.data) {
    const body = response.data as { report_id: string; status: string }
    report.value = { id: body.report_id, status: body.status }
    pollFailures = 0
    poll = setInterval(() => void checkReport(), 5_000)
  } else {
    error.value = 'Could not schedule. Check the backend connection.'
    logger.warn('export_schedule_failed', { status: response.response?.status })
  }
}
/* Polling never fails silently (audit F-11): auth/gone → terminal at once; transient
 * errors get a bounded number of retries before the dialog says so and stops. */
const POLL_MAX_FAILURES = 6
let pollFailures = 0
function stopPolling() {
  if (poll) clearInterval(poll)
  poll = null
}
async function checkReport() {
  if (!report.value) return
  const response = await getReportApiV1ReportsReportIdGet({ path: { report_id: report.value.id } })
  if (!response.response?.ok || !response.data) {
    const status = response.response?.status ?? 0
    if (status === 401 || status === 403 || status === 404 || status === 410) {
      stopPolling()
      error.value =
        status === 401 || status === 403
          ? 'Session expired while waiting. Sign in again: the report keeps running and rings the bell.'
          : 'The scheduled report is gone (expired or removed). Re-run the export.'
      logger.warn('export_poll_terminal', { status, report_id: report.value.id })
    } else if (++pollFailures >= POLL_MAX_FAILURES) {
      stopPolling()
      error.value = 'Lost contact with the backend while polling. The bell will ring when the report is ready.'
      logger.warn('export_poll_gave_up', { status, report_id: report.value.id })
    }
    return
  }
  pollFailures = 0
  const body = response.data as {
    status: string
    download_token?: string
    expires_at?: string
  }
  report.value = {
    id: report.value.id,
    status: body.status,
    token: body.download_token,
    expires_at: body.expires_at,
  }
  if (body.status === 'done' || body.status === 'failed') stopPolling()
}
const downloadHref = computed(() =>
  report.value?.token
    ? `/api/v1/reports/${report.value.id}/download?token=${encodeURIComponent(report.value.token)}`
    : null,
)
</script>

<template>
  <div class="export-wrap">
    <UiButton variant="control" @click="openDialog">
      <AppIcon name="download" :size="13" />Export CSV
    </UiButton>

    <ModalShell
      v-if="open"
      title="Export"
      subtitle="what you are looking at now · scanners are never merged (a VEX file holds one scanner)"
      :width="480"
      @close="close"
    >
          <p v-if="historical" class="ex-blocked">
            <AppIcon name="clock" :size="13" />
            Rewound lens: the export is queued off-peak and reconstructs the rows
            <strong>as they stood at T</strong> (Run now streams current state only).
          </p>
            <UiSegControl v-if="!historical" v-model="tab" class="tabs" :options="TAB_OPTS" />

            <UiField label="Format">
              <UiSegControl v-model="format" :options="FORMAT_OPTS" />
            </UiField>
            <div v-if="format === 'vex'" class="vex-scanner">
              <UiField label="Scanner (one per VEX file)">
                <UiSegControl v-model="vexScanner" :options="SCANNER_OPTS" />
              </UiField>
            </div>

            <template v-if="tab === 'now'">
              <p v-if="blocked" class="ex-blocked"><AppIcon name="alert" :size="13" /> {{ blocked }}</p>
              <p v-else class="ex-note">Streams up to the inline cap; a bigger lens gets a 413 and the schedule path.</p>
            </template>
            <template v-else>
              <p v-if="blocked" class="ex-blocked"><AppIcon name="alert" :size="13" /> {{ blocked }}</p>
              <p v-else class="ex-note">Runs in the off-peak window; the result keeps for ~24h after completion.</p>
              <div v-if="report" class="report-status">
                <template v-if="report.status === 'done' && downloadHref">
                  <AppIcon name="check" :size="13" />
                  <a :href="downloadHref" class="dl-link">Download</a>
                  <span class="ex-dim">{{ expiresIn(report.expires_at) }}</span>
                </template>
                <template v-else-if="report.status === 'failed'">
                  <AppIcon name="alert" :size="13" /> Report failed. Re-run the export.
                </template>
                <template v-else>
                  <AppIcon name="clock" :size="13" /> Scheduled, status: {{ report.status }}…
                </template>
              </div>
            </template>

            <p v-if="error" class="modal-error" role="alert">{{ error }}</p>

      <template #actions>
          <UiButton variant="ghost" @click="close">Close</UiButton>
          <UiButton
            v-if="tab === 'now'"
            variant="primary"
            :disabled="busy || exporting || !!blocked"
            @click="runNow"
          >
            {{ exporting ? 'Exporting…' : 'Download' }}
          </UiButton>
          <UiButton
            v-else
            variant="primary"
            :disabled="busy || exporting || !!blocked || report !== null"
            @click="schedule"
          >
            {{ busy ? 'Scheduling…' : 'Schedule' }}
          </UiButton>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.export-wrap {
  display: inline-flex;
}
.tabs {
  margin-bottom: 4px;
}
.vex-scanner {
  margin-top: 2px;
}
.ex-note {
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
.ex-blocked {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin: 10px 0 0;
  font-size: var(--text-body);
  color: var(--ink);
  background: var(--hist-bg);
  border: 1px solid var(--hist-line);
  border-radius: var(--r-sm);
  padding: 10px 12px;
  line-height: 1.5;
}
.ex-blocked svg {
  flex: none;
  margin-top: 2px;
  color: var(--hist-fg);
}
.report-status {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-top: 12px;
  font-size: var(--text-body);
  color: var(--ink);
}
.dl-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.ex-dim {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
</style>

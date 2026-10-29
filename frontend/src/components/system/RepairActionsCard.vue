<script setup lang="ts">
/**
 * The two job cards of the Data inspector, both fed by /api/v1/admin/jobs (one fetch, one poll
 * while anything runs) and both drawn with JobsTable.
 *
 * Repair actions (issue 406): "something looks broken" never means raw writes. The three
 * sanctioned, journaled jobs are the fix, each with a Run button. Lifecycle DROPS whole indices,
 * so its button confirms through ModalShell first, and it carries a Dry run (issue 459): an
 * inline would-roll/would-drop answer that changes nothing.
 *
 * Scheduled jobs (issue 556): the jobs the backend only ever runs on its schedule. The same
 * table, read-only.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { client } from '@/api/client'
import { listJobsApiV1AdminJobsGet, triggerJobApiV1AdminJobsKindRunPost } from '@/api/generated'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'
import type { JobDoc } from '@/system/inspect'

import JobsTable from './JobsTable.vue'

const LABEL: Record<string, string> = {
  rebuild_state: 'Rebuild state',
  staleness_sweep: 'Staleness sweep',
  lifecycle_sweep: 'Lifecycle sweep',
}

const auth = useAuthStore()
const toast = useToastStore()
const all = ref<JobDoc[]>([])
const scheduler = ref<{ enabled: boolean; timezone: string } | null>(null)
const jobs = computed(() => all.value.filter((j) => j.runnable))
const scheduled = computed(() => all.value.filter((j) => !j.runnable))
const loaded = ref(false)
const failed = ref(false)
const confirming = ref<JobDoc | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

async function refresh() {
  const r = await listJobsApiV1AdminJobsGet({ client })
  if (r.response?.ok && r.data) {
    const body = r.data as { jobs: JobDoc[]; scheduler?: { enabled: boolean; timezone: string } }
    all.value = body.jobs
    scheduler.value = body.scheduler ?? null
    failed.value = false
  } else {
    failed.value = true
  }
  loaded.value = true
  syncPolling()
}

const anyRunning = computed(() => all.value.some((j) => j.status === 'running' && !j.stale))

function syncPolling() {
  if (anyRunning.value && timer === null) {
    timer = setInterval(() => void refresh(), 3000)
  } else if (!anyRunning.value && timer !== null) {
    clearInterval(timer)
    timer = null
  }
}

onMounted(() => void refresh())
onUnmounted(() => {
  if (timer !== null) clearInterval(timer)
})

function requestRun(job: JobDoc) {
  if (job.kind === 'lifecycle_sweep') {
    confirming.value = job // destructive tier — say what it deletes before it deletes
  } else {
    void run(job)
  }
}

async function run(job: JobDoc) {
  confirming.value = null
  const r = await triggerJobApiV1AdminJobsKindRunPost({ client, path: { kind: job.kind } })
  if (r.response?.status === 202) {
    logger.info('repair_job_triggered', { kind: job.kind })
    await refresh()
  } else {
    const problem = (r.error ?? null) as { title?: string } | null
    toast.info(problem?.title ?? `${LABEL[job.kind] ?? job.kind} could not start.`)
    logger.warn('repair_job_rejected', { kind: job.kind, status: r.response?.status })
    await refresh() // a 409 means someone else is running it — show that truth
  }
}

const dryRunning = ref(false)

async function dryRun(job: JobDoc) {
  dryRunning.value = true
  try {
    const r = await triggerJobApiV1AdminJobsKindRunPost({
      client,
      path: { kind: job.kind },
      query: { dry_run: true },
    })
    if (r.response?.status === 200 && r.data) {
      const { rolled, dropped, errors } = (r.data as { result: Record<string, number> }).result
      const trouble = errors ? ` ${errors} series could not be checked.` : ''
      toast.info(
        rolled || dropped
          ? `Dry run: the sweep would roll over ${rolled} and delete ${dropped} indices.${trouble} Nothing was changed.`
          : `Dry run: nothing is due to roll over or be deleted.${trouble}`,
      )
      logger.info('repair_job_dry_run', { kind: job.kind, rolled, dropped, errors })
    } else {
      const problem = (r.error ?? null) as { title?: string } | null
      toast.info(problem?.title ?? 'The dry run could not start.')
      logger.warn('repair_job_dry_run_rejected', { kind: job.kind, status: r.response?.status })
    }
  } finally {
    dryRunning.value = false
  }
}

function canRun(job: JobDoc): boolean {
  return job.capability !== null && auth.hasCapability(job.capability)
}
</script>

<template>
  <section class="tbl-card repair">
    <h2 class="panel-band">Repair actions</h2>
    <p class="repair-sub">
      If the data on screen looks wrong, these are the safe, built-in fixes. They recompute
      from the stored scan history instead of editing anything by hand. Every run is recorded
      in the audit log.
    </p>
    <p v-if="failed" class="load-error" role="alert">
      Job status unavailable. The triggers are disabled until it loads.
    </p>
    <JobsTable v-else-if="loaded" :jobs="jobs">
      <template #actions="{ job }">
        <div class="repair-buttons">
          <UiButton
            v-if="job.kind === 'lifecycle_sweep'"
            variant="control"
            :disabled="!canRun(job) || dryRunning"
            :title="canRun(job) ? 'See what the sweep would delete. Changes nothing' : `Requires ${job.capability}`"
            @click="dryRun(job)"
          >
            {{ dryRunning ? 'Checking…' : 'Dry run' }}
          </UiButton>
          <UiButton
            :variant="job.status === 'running' && !job.stale ? 'control' : 'primary'"
            :disabled="!canRun(job) || (job.status === 'running' && !job.stale)"
            :title="canRun(job) ? undefined : `Requires ${job.capability}`"
            @click="requestRun(job)"
          >
            {{ job.status === 'running' && !job.stale ? 'Running…' : 'Run' }}
          </UiButton>
        </div>
      </template>
    </JobsTable>

    <ModalShell v-if="confirming" title="Run the lifecycle sweep?" @close="confirming = null">
      <p class="confirm-body">
        This applies retention by <b>deleting whole aged indices</b>: findings history past each
        cluster's retention window is gone for good, and time-travel can no longer reach it.
        The sweep is journaled and follows the same rules as the scheduled run. Not sure?
        Cancel and press <b>Dry run</b> first: it shows what would be deleted without
        changing anything.
      </p>
      <template #actions>
        <UiButton variant="ghost" @click="confirming = null">Cancel</UiButton>
        <UiButton variant="primary" @click="run(confirming)">Run the sweep</UiButton>
      </template>
    </ModalShell>
  </section>

  <section v-if="loaded && !failed && scheduled.length" class="tbl-card repair scheduled">
    <h2 class="panel-band">Scheduled jobs</h2>
    <p class="repair-sub">
      The backend runs these on its own. Schedules are cron expressions set in the
      deployment<template v-if="scheduler"> and read in the server timezone ({{ scheduler.timezone }})</template
      >.
      <b v-if="scheduler && !scheduler.enabled">
        The scheduler is switched off on this backend, so nothing here runs on its own.
      </b>
    </p>
    <JobsTable :jobs="scheduled" />
  </section>
</template>

<style scoped>
.repair {
  margin-top: var(--space-6);
}
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
.repair-sub {
  color: var(--soft);
  font-size: var(--text-body);
  margin: 12px 16px;
  max-width: 88ch;
}
.repair-sub b {
  color: var(--ink);
  font-weight: 600;
}
.load-error {
  margin: 4px 16px 12px;
}
.repair-buttons {
  display: inline-flex;
  gap: 8px;
}
.confirm-body {
  margin: 0;
  color: var(--soft);
  font-size: var(--text-body);
  max-width: 60ch;
}
.confirm-body b {
  color: var(--ink);
}
</style>

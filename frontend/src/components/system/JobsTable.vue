<script setup lang="ts">
/**
 * The background jobs as a table (issue 556): Job, Schedule, Last run, Next run, Status, and an
 * actions column when the host gives one. Both cards on the Data inspector draw their rows with
 * it, so a job reads the same whether or not it has a Run button. The shared table skin does
 * the head and the row lines; a card narrower than the table scrolls it sideways.
 */
import DotWord from '@/components/chips/DotWord.vue'
import AppIcon, { type IconName } from '@/components/ui/AppIcon.vue'
import { fmtAt } from '@/findings/format'
import { jobFlag, jobLastRun, jobNextRun, jobSchedule, type JobDoc } from '@/system/inspect'

defineProps<{ jobs: JobDoc[] }>()

const COPY: Record<string, { icon: IconName; label: string; desc: string }> = {
  rebuild_state: {
    icon: 'rescan',
    label: 'Rebuild state',
    desc: 'Builds each current row again from the history. This repairs the data after a crash. You can run it at any time. It never changes the history.',
  },
  staleness_sweep: {
    icon: 'clock',
    label: 'Staleness sweep',
    desc: 'Sets the stale marks now. It does not wait for the scheduled run.',
  },
  lifecycle_sweep: {
    icon: 'trash',
    label: 'Lifecycle sweep',
    desc: 'Starts a new history index when the old one is full or old. It deletes the indices that are older than the retention window. No other job deletes history.',
  },
  report_drain: {
    icon: 'download',
    label: 'Export queue',
    desc: 'Builds the exports people have asked for.',
  },
  report_sweep: {
    icon: 'clock',
    label: 'Export cleanup',
    desc: 'Deletes complete and failed exports after their keep time. It also deletes the parts of exports that stopped.',
  },
  findings_cleanup: {
    icon: 'trash',
    label: 'Old findings cleanup',
    desc: 'Deletes the findings that are gone for longer than the findings cleanup window.',
  },
  session_sweep: {
    icon: 'key',
    label: 'Expired sessions',
    desc: 'Deletes the sign-in sessions that expired.',
  },
}
</script>

<template>
  <div class="tbl-wrap">
    <table class="tbl tbl-hover jobs">
      <thead>
        <tr>
          <th>Job</th>
          <th>Schedule</th>
          <th>Last run</th>
          <th>Next run</th>
          <th>Status</th>
          <th v-if="$slots.actions" aria-label="Actions" />
        </tr>
      </thead>
      <tbody>
        <tr v-for="job in jobs" :key="job.kind" class="repair-row">
          <td class="job-cell">
            <div class="job-id">
              <span class="job-tile"><AppIcon :name="COPY[job.kind]?.icon ?? 'gear'" :size="16" /></span>
              <div>
                <b>{{ COPY[job.kind]?.label ?? job.kind }}</b>
                <p>{{ COPY[job.kind]?.desc }}</p>
              </div>
            </div>
          </td>
          <td class="mono" :class="{ quiet: !job.schedule }">{{ jobSchedule(job) }}</td>
          <td class="mono last-cell">
            <div v-if="job.status === 'running' && !job.stale" class="job-runbar" aria-hidden="true" />
            <div
              class="job-meta"
              :class="{ 'job-failed': jobLastRun(job, fmtAt).bad, quiet: job.status === 'idle' }"
            >
              {{ jobLastRun(job, fmtAt).line }}
              <small v-if="jobLastRun(job, fmtAt).detail">{{ jobLastRun(job, fmtAt).detail }}</small>
            </div>
          </td>
          <td class="mono" :class="{ quiet: !job.next_run_at }">{{ jobNextRun(job, fmtAt) }}</td>
          <td><DotWord v-bind="jobFlag(job)" /></td>
          <td v-if="$slots.actions" class="act"><slot name="actions" :job="job" /></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
/* below this the columns would crush the job's description; a narrower card scrolls the table */
.jobs {
  min-width: 760px;
}
.jobs td {
  font-size: var(--text-body);
}
.job-cell {
  width: 34%;
}
.job-id {
  display: flex;
  align-items: center;
  gap: 14px;
}
.job-tile {
  display: grid;
  place-items: center;
  flex: none;
  width: 34px;
  height: 34px;
  border-radius: var(--r-sm);
  background: var(--panel);
  border: 1px solid var(--line2);
  color: var(--soft);
}
.job-id b {
  display: block;
}
.job-id p {
  margin: 2px 0 0;
  color: var(--soft);
  font-size: var(--text-control);
  max-width: 56ch;
}
.jobs td.mono {
  font-family: var(--font-mono);
  font-size: var(--text-control);
  white-space: nowrap;
}
.jobs td.last-cell {
  white-space: normal;
  min-width: 160px;
}
.quiet {
  color: var(--soft);
}
.job-meta small {
  display: block;
  margin-top: 2px;
  color: var(--soft);
  font-size: var(--text-sm);
  overflow-wrap: anywhere;
}
.job-failed,
.job-failed small {
  color: var(--health-down-fg);
}
.act {
  text-align: right;
  white-space: nowrap;
}
/* the in-flight indicator: the same infinite-bar grammar as the console's runbar. Result counts
   land the moment the run finishes (no percentage: the jobs report counts, not progress) */
.job-runbar {
  height: 4px;
  border-radius: 2px;
  background: var(--line2);
  overflow: hidden;
  position: relative;
  margin-bottom: 5px;
}
.job-runbar::after {
  content: '';
  position: absolute;
  inset: 0;
  width: 38%;
  background: var(--coral);
  border-radius: 2px;
  animation: repair-sweep 1.1s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
@keyframes repair-sweep {
  from {
    transform: translateX(-110%);
  }
  to {
    transform: translateX(300%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .job-runbar::after {
    animation: none;
    width: 100%;
    opacity: 0.45;
  }
}
</style>

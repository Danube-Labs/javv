<script setup lang="ts">
/** Written in Simplified Technical English (issue 1142). The job names are the ones of
 * `RepairActionsCard.vue`, and the role comes from `jobs/registry.py` and the route of the page. */
import GuideProse from './GuideProse.vue'
</script>

<template>
  <GuideProse>
    <p>The Data inspector shows the data of JAVV in OpenSearch. It has two cards of jobs.</p>
    <ul>
      <li class="repair-jobs">
        <span class="ui-name">Repair actions</span> has three jobs: Rebuild state, Staleness sweep and
        Lifecycle sweep. Each job has <span class="ui-name">Run</span>. Use these jobs when the data on a
        screen looks wrong. The Audit log records each run.
      </li>
      <li>
        The Lifecycle sweep deletes old indices. It asks before it runs. Its
        <span class="ui-name">Dry run</span> shows what it deletes, and changes nothing.
      </li>
      <li>
        <span class="ui-name">Scheduled jobs</span> shows the jobs that JAVV runs only on its schedule.
        These jobs have no Run.
      </li>
      <li>Each card shows the schedule, the last run, the next run and the status of each job.</li>
      <li>To open the Data inspector and run a job, you need the admin role.</li>
    </ul>
  </GuideProse>
</template>

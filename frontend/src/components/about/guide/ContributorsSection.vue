<script setup lang="ts">
/** Written in Simplified Technical English (issue 1142). The handled actions are
 * `HANDLING_ACTIONS` of `query/contributors.py`, named by the action names of the Audit log. */
import { ACTION_LABELS } from '@/audit/actionLabels'

import GuideProse from './GuideProse.vue'

const HANDLED = (['acknowledge', 'not_affected', 'risk_accept', 'resolve'] as const).map((a) => ACTION_LABELS[a])
</script>

<template>
  <GuideProse>
    <p>
      The numbers come from the Audit log, not from the scans. They count the triage work in the time
      range.
    </p>
    <ul>
      <li class="handled">
        Handled counts these actions: {{ HANDLED.slice(0, -1).join(', ') }} and {{ HANDLED.at(-1) }}.
      </li>
      <li>
        <span class="ui-name">SLA met</span> is the part of the handled findings that got their action
        before the SLA deadline. The deadline comes from the severity of the finding and from KEV.
      </li>
      <li>The podium shows the first three people. The table shows at most 100 people.</li>
      <li>The order is the number of resolved findings, then the number of handled findings.</li>
    </ul>
  </GuideProse>
</template>

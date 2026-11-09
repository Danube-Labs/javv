<script setup lang="ts">
/** Written in Simplified Technical English (issue 1142). The steps are on the docs page Build a
 * dashboard, so the section links to it and does not copy them. The words of the panel scanner
 * setting come from `PANEL_SCANNER_OPTS`. */
import { onMain } from '@/about/links'
import { PANEL_SCANNER_OPTS } from '@/dashboards/edit'

import GuideProse from './GuideProse.vue'

const FOLLOW = PANEL_SCANNER_OPTS[0].label
const DOCS = onMain('docs/use/build-a-dashboard.md')
</script>

<template>
  <GuideProse>
    <p>
      A dashboard puts panels of Overview, Contributors and Scanner status on one page. Each panel shows
      the data of the selected cluster and the time range.
    </p>
    <ul>
      <li>To make a dashboard, your role must allow dashboards.</li>
      <li>The scanner switch at the top sets the scanner of the dashboard.</li>
      <li class="panel-scanner">
        Each panel has a scanner setting. <span class="ui-name">{{ FOLLOW }}</span> uses the switch.
        <code class="mono">trivy</code> or <code class="mono">grype</code> keeps the panel on one scanner.
      </li>
      <li>
        Some panels have filters, for example a severity or a namespace. A panel with filters shows the
        number of its filters.
      </li>
      <li>
        You can share a dashboard with all users or with some roles. Only the owner and the admin role can
        change it.
      </li>
      <li>
        <span class="ui-name">Export</span> and <span class="ui-name">Import</span> copy dashboards to a
        different JAVV.
      </li>
    </ul>
    <p>
      The page <a class="docs-link" :href="DOCS" target="_blank" rel="noopener noreferrer">Build a dashboard</a>
      gives the steps.
    </p>
  </GuideProse>
</template>

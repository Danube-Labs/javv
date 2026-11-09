<script setup lang="ts">
/** Written in Simplified Technical English (issue 1142). The defaults are `JAVV_EXPORT_MAX_ROWS`
 * and `JAVV_EXPORT_TTL_HOURS` of docs/CONFIGURATION.md: the backend can have other values, so the
 * text says "by default". The tab names are the ones of `ExportDialog.vue`. */
import GuideProse from './GuideProse.vue'
</script>

<template>
  <GuideProse>
    <p>
      <span class="ui-name">Export</span> on Findings gives a CSV file or a VEX file of the findings that
      the filters show.
    </p>
    <ul>
      <li>
        <span class="ui-name">Run now</span> downloads the file at once. It has a limit of 50,000 rows by
        default.
      </li>
      <li>
        <span class="ui-name">In the background</span> has no row limit. JAVV makes the file, and the bell
        tells you when it is ready.
      </li>
      <li>JAVV keeps a file from In the background for 24 hours by default.</li>
      <li>A VEX file holds the findings of one scanner. Select the scanner before you export.</li>
      <li>
        When you look at a past time, only In the background is available. The file has the rows as they
        were at that time.
      </li>
      <li>The Audit log, Contributors and the Approval list also download a CSV file, with the same row limit.</li>
      <li>To export, your role must allow export.</li>
    </ul>
  </GuideProse>
</template>

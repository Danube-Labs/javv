<script setup lang="ts">
import GuideProse from './GuideProse.vue'
</script>

<template>
  <GuideProse>
    <p>The range in the top bar drives every screen at once.</p>
    <ul>
      <li>
        <strong>Tables show what was true at the end of the range.</strong> Pick
        <span class="ui-name">Last 24 hours</span> and the findings table still lists everything that was
        vulnerable at that moment, not only what was found in those 24 hours. When the scanners were
        quiet, the table stays full.
      </li>
      <li>
        <strong>Charts show what happened inside the range,</strong> like the ingest strip above the
        tables, which counts the scans as they arrived.
      </li>
      <li>
        <strong>Move the end into the past to see history.</strong> Screens then show JAVV as it was
        scanned at that moment, triage included. Clicking a day on the ingest strip does the same for
        the end of that day. A banner says you're viewing history, and
        <span class="ui-name">Back to now</span> returns. The few screens that only make sense now, like
        the <span class="ui-name">Approval list</span>, tell you so.
      </li>
    </ul>
  </GuideProse>
</template>

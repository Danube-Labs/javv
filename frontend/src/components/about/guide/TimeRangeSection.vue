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
        <strong>Charts show what happened inside the range,</strong> for example the Scan ingest strip
        above the tables. It counts the scans when they arrived.
      </li>
      <li>
        <strong>Move the end into the past to see history.</strong> The screens then show JAVV as the
        scans saw it at that time, with the triage of that time. A click on a day of the Scan ingest strip
        does the same for the end of that day. A banner tells you that you see history.
        <span class="ui-name">Back to now</span> goes back to the time now. The few screens that only make sense now, like
        the <span class="ui-name">Approval list</span>, tell you so.
      </li>
    </ul>
  </GuideProse>
</template>

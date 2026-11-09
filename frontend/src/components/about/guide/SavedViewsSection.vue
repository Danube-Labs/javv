<script setup lang="ts">
/** Written in Simplified Technical English (issue 1142). The reader is "you" (the voice rule of
 * the Guide). What a view keeps and who deletes it come from `routers/views.py`. */
import GuideProse from './GuideProse.vue'
</script>

<template>
  <GuideProse>
    <p>
      A saved view keeps the filters, the columns, the row density, the sort and the time window of
      Findings. It does not keep the cluster.
    </p>
    <ul>
      <li>To save a view, set up Findings. Then select <span class="ui-name">Save view</span>.</li>
      <li>Each user of JAVV sees the views that you save.</li>
      <li>You can delete a view that you saved. The admin role can delete each view.</li>
      <li>To change a view, delete it and save it again.</li>
      <li class="view-count">
        The number on a card is the count of the findings that match the view. It counts in the
        selected cluster, at the end of the time range.
      </li>
    </ul>
  </GuideProse>
</template>

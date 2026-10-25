<script setup lang="ts">
/**
 * The grid of saved-item cards and the pager bar under it (SCREENS §6), shared by Saved views
 * and Dashboards. The pager lives in a slim card of its own, since the cards are the rows.
 */
</script>

<template>
  <div class="views-grid"><slot /></div>
  <div v-if="$slots.pager" class="views-pager"><slot name="pager" /></div>
</template>

<style scoped>
.views-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
  margin-top: 16px;
}
.views-pager {
  margin-top: 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
/* the card IS the container — the pager's own in-table top rule would double the border */
.views-pager :deep(.pager) {
  border-top: 0;
}
</style>

<script setup lang="ts">
/**
 * One card of a saved-items grid (SCREENS §6): Saved views and Dashboards share it. The title,
 * a badge or a remove button (the remove button only for a user who may remove the item), a
 * description and a summary line, then a footer: the item's number, its owner and its actions.
 */
defineProps<{ title: string; description?: string; summary?: string; owner: string; removeLabel?: string }>()
defineEmits<{ remove: [] }>()
</script>

<template>
  <article class="view-card">
    <div class="vc-head">
      <h2>{{ title }}</h2>
      <span v-if="$slots.badge" class="vc-badge"><slot name="badge" /></span>
      <button v-if="removeLabel" type="button" class="vc-x" :aria-label="removeLabel" @click="$emit('remove')">
        ×
      </button>
    </div>
    <p v-if="description" class="vc-desc">{{ description }}</p>
    <p class="vc-summary"><slot name="summary">{{ summary }}</slot></p>
    <div class="vc-foot">
      <span class="vc-count"><slot name="stat" /></span>
      <span class="vc-owner mono">{{ owner }}</span>
      <slot name="actions" />
    </div>
  </article>
</template>

<style scoped>
.view-card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.view-card:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.vc-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.vc-head h2 {
  margin: 0;
  font-size: var(--text-body);
  font-weight: 600;
}
.vc-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: none;
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-chip);
  font-size: var(--text-sm);
  color: var(--soft);
}
.vc-x {
  border: 0;
  background: transparent;
  color: var(--soft);
  font-size: var(--text-body);
  line-height: 1;
  padding: 2px 6px;
  border-radius: var(--r-sm);
  cursor: default;
}
.vc-x:hover {
  background: var(--fpill-x-hover-bg);
  color: var(--coral-text);
}
.vc-desc {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--ink);
}
.vc-summary {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--soft);
  font-style: italic;
}
.vc-foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: auto;
  padding-top: 6px;
}
.vc-count {
  font-weight: 600;
  font-size: var(--text-sm);
}
.vc-owner {
  flex: 1;
  font-size: var(--text-facet-label);
  color: var(--soft);
}
</style>

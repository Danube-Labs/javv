<script setup lang="ts">
/**
 * Scanner-disagreement flag (prototype `.disagree-tag`; D5a/N10). `disagree` is a BOOL on the
 * row (A-3) — the other scanner's verbatim severity comes from the sibling-row query, which is
 * the detail panel's job (slice 2); the grid badge just flags it. Never merges or reconciles.
 */
import AppIcon from '@/components/ui/AppIcon.vue'

/** `label` spells the flag out in words — surfaces with room (the detail head) say it,
 * dense grid rows keep the bare chip. */
defineProps<{ title?: string; label?: string }>()
</script>

<template>
  <span class="disagree-tag" :title="title ?? 'The scanners do not agree on this finding.'">
    <AppIcon name="alert" :size="11" />±<span v-if="label" class="dt-label">{{ label }}</span>
  </span>
</template>

<style scoped>
.disagree-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  font-weight: 700;
  color: var(--sev-medium-fg);
  background: var(--sev-medium-bg);
  border: 1px solid var(--sev-medium-line);
  padding: 2.5px 6px;
  border-radius: 5px;
  cursor: help;
}
.dt-label {
  margin-left: 3px;
  font-family: var(--font-ui);
  font-weight: 600;
}
</style>

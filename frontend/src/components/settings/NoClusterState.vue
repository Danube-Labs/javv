<script setup lang="ts">
/**
 * A per-cluster settings page before any cluster is listed (issue 817, finding 3): its read needs
 * a cluster id, so it would otherwise wait on its loading placeholder forever. A cluster is
 * listed once its first token exists, which is what the copy points at.
 */
import EmptyState from '@/components/ui/EmptyState.vue'
</script>

<template>
  <EmptyState
    icon="layers"
    title="Settings for a cluster appear once it has a scanner token."
    hint="Mint one under Access & tokens."
  />
</template>

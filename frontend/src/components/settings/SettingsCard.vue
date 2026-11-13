<script setup lang="ts">
/**
 * Settings panel card (prototype screens-config.jsx `Card`): title + subtitle head, optional
 * action slot, set-row body. Every M9e panel composes these — never re-roll the card chrome.
 */
defineProps<{ title: string; subtitle?: string }>()
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div>
        <!-- h2, not the app-wide card h3: settings panels sit directly under the page h1 -->
        <h2><slot name="title">{{ title }}</slot></h2>
        <p v-if="subtitle" class="card-sub">{{ subtitle }}</p>
      </div>
      <slot name="action" />
    </div>
    <div class="card-body"><slot /></div>
  </section>
</template>

<style scoped>
.card {
  overflow: hidden;
}
.card-head {
  align-items: flex-start;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line2);
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.card-body {
  padding: 4px 16px 14px;
}
</style>

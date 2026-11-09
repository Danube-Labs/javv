<script setup lang="ts">
/** Reading text for one guide section: paragraph and list rhythm, so every section sets its
 * words the same way. No measure cap: the text fills its card at any window width (operator
 * ruling 2026-10-01, the 72ch column left most of a wide card empty). */
</script>

<template>
  <div class="guide-prose"><slot /></div>
</template>

<style scoped>
.guide-prose {
  color: var(--ink);
  font-size: var(--text-body);
  line-height: 1.6;
}
.guide-prose :slotted(p) {
  margin: 0 0 var(--space-3);
}
.guide-prose :slotted(ul),
.guide-prose :slotted(ol) {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: 0 0 var(--space-3);
  padding-left: 18px;
}
/* numbers need more room than bullets once a list reaches ten steps */
.guide-prose :slotted(ol) {
  padding-left: 24px;
}
.guide-prose :slotted(:last-child) {
  margin-bottom: 0;
}
.guide-prose :slotted(strong) {
  font-weight: 600;
}
.guide-prose :slotted(.ui-name) {
  font-weight: 600;
  white-space: nowrap;
}
.guide-prose :slotted(.docs-link) {
  text-decoration: underline;
  text-underline-offset: 2px;
}
.guide-prose :slotted(.docs-link:hover) {
  color: var(--ink);
}
</style>

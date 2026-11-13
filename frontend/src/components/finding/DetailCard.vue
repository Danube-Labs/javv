<script setup lang="ts">
/**
 * Detail-page card chrome (issue 434): title + optional subtitle head, action/tag slot,
 * body. Replaces the four per-component copies of the same scoped block ("the DecisionsCard
 * idiom" — which was the debt, not the pattern). `flush` drops the body padding so a kit
 * `.tbl-wrap` runs edge-to-edge under the head, the way every grid card does; put prose
 * in a `.card-notes` strip after the table.
 */
/** `darkHead` opts the head into the B2 slate band — ONLY where the operator ruled it
 * (triage panel, activity card); the default head stays on the parchment register. */
defineProps<{ title: string; sub?: string; flush?: boolean; darkHead?: boolean }>()
</script>

<template>
  <section class="card">
    <div class="card-head" :class="{ dark: darkHead }">
      <div>
        <h2><slot name="title">{{ title }}</slot></h2>
        <p v-if="sub" class="card-sub">{{ sub }}</p>
      </div>
      <slot name="action" />
    </div>
    <div class="card-body" :class="{ flush }"><slot /></div>
  </section>
</template>

<style scoped>
.card {
  overflow: hidden;
  /* fill the grid track when stretched — equal-height rows leave slack INSIDE the card,
     absorbed above the pager/notes, never as dead page space (operator, 2026-07-17) */
  height: 100%;
  display: flex;
  flex-direction: column;
}
.card-head {
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line2);
}
/* the B2 slate band — opt-in per operator ruling 2026-07-17 (activity; triage has its own) */
.card-head.dark {
  background: var(--table-head-bg);
  color: var(--table-head-fg);
  border-bottom: 0;
}
.card-head.dark .card-sub {
  color: inherit;
  opacity: 0.75;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.card-body {
  padding: 14px 16px;
  flex: 1;
}
.card-body.flush {
  padding: 0;
  display: flex;
  flex-direction: column;
}
/* slack sinks between the table and whatever closes the card */
.card-body.flush :deep(.pager),
.card-body.flush :deep(.card-notes) {
  margin-top: auto;
}
.card-body.flush :deep(.pager ~ .card-notes) {
  margin-top: 0;
}
/* the kit table sheds its own card chrome inside this card (the .tbl-card rule's sibling) */
.card-body.flush :deep(.tbl-wrap) {
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.card-body :deep(.card-notes) {
  padding: 12px 16px;
  border-top: 1px solid var(--line2);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>

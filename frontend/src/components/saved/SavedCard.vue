<script setup lang="ts">
/**
 * One card of a saved-items grid (SCREENS §6): Saved views and Dashboards share it. The title,
 * a badge or a remove button (the remove button only for a user who may remove the item), a
 * description and a summary line, then a footer: the item's number, its owner, its actions and,
 * when the screen gives an `openLabel`, a quiet "<label> ›" that says where the card goes.
 *
 * The whole card opens the item (issue 1004): the title is a RowLink whose ::after covers the
 * card, so a click anywhere opens it, Tab reaches it once, and a ctrl click opens a new tab. The
 * badge, the remove button and the actions sit above that layer and keep their own clicks.
 */
import type { RouteLocationRaw } from 'vue-router'

import RowLink from '@/components/ui/RowLink.vue'

defineProps<{
  title: string
  to: RouteLocationRaw
  openLabel?: string
  description?: string
  summary?: string
  owner: string
  removeLabel?: string
}>()
defineEmits<{ open: []; remove: [] }>()
</script>

<template>
  <article class="view-card">
    <div class="vc-head">
      <h2>
        <RowLink class="vc-link" :to="to" @open="$emit('open')">{{ title }}</RowLink>
      </h2>
      <span v-if="$slots.badge" class="vc-badge"><slot name="badge" /></span>
      <button v-if="removeLabel" type="button" class="vc-x" :aria-label="removeLabel" @click="$emit('remove')">
        ×
      </button>
    </div>
    <p v-if="description" class="vc-desc">{{ description }}</p>
    <p class="vc-summary"><slot name="summary">{{ summary }}</slot></p>
    <div class="vc-foot">
      <span class="vc-count"><slot name="stat" /></span>
      <span class="vc-owner">Owner <b class="vc-owner-name">{{ owner }}</b></span>
      <slot name="actions" />
      <span v-if="openLabel" class="vc-open" aria-hidden="true">{{ openLabel }} <span class="vc-open-mark">›</span></span>
    </div>
  </article>
</template>

<style scoped>
.view-card {
  position: relative;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition:
    border-color var(--dur-quick) var(--ease-out),
    transform var(--dur-quick) var(--ease-out);
}
/* the prototype's clickable card (DESIGN.md §5): it stays white, so a button's hover wash inside
   it always shows; a fill here gave the button and the card one color (issue 1004) */
.view-card:hover,
.view-card:has(.vc-link:focus-visible) {
  border-color: var(--coral);
  transform: translateY(-1px);
}
.view-card:has(.vc-link:active) {
  transform: none;
}
.vc-link::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
}
.vc-badge,
.vc-x,
.vc-foot :slotted(.ui-btn) {
  position: relative;
  z-index: 1;
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
/* a long role list must not push the badge out of the card: it gives way, and its text ends
   in "…" (the full text is its title) */
.vc-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 1 auto;
  min-width: 0;
  max-width: 60%;
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-chip);
  font-size: var(--text-sm);
  color: var(--soft);
}
.vc-badge :slotted(.vc-badge-text) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  padding-top: 10px;
  border-top: 1px solid var(--line2);
}
.vc-count {
  font-weight: 600;
  font-size: var(--text-sm);
}
/* the size of the other card text: at the 10px label size the name was hard to read (issue 1004) */
.vc-owner {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--soft);
}
.vc-owner-name {
  color: var(--ink);
  font-weight: 600;
}
.vc-open {
  white-space: nowrap;
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--soft);
}
.vc-open-mark {
  color: var(--dash-muted);
}
.view-card:hover .vc-open,
.view-card:hover .vc-open-mark {
  color: var(--coral-text);
}
@media (prefers-reduced-motion: reduce) {
  .view-card {
    transition: none;
  }
  .view-card:hover,
  .view-card:has(.vc-link:focus-visible) {
    transform: none;
  }
}
</style>

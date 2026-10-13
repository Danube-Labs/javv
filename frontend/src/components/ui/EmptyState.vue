<script setup lang="ts">
/**
 * Kit empty state (M9f, SCREENS.md §15 "first-run/empty states on every data screen — M9f owns
 * the shared components"): the one centered no-data grammar — stroke icon in a soft tile,
 * ink title, soft hint, optional action row (default slot). Covers first-run, cold-start and
 * filtered-empty copy; in-table empties keep the base.css `.empty-row` register (a table row
 * is not a page state).
 */
import AppIcon, { type IconName } from '@/components/ui/AppIcon.vue'

defineProps<{
  icon?: IconName
  title: string
  hint?: string
  /** the state IS the page (the cold start): its title is the page's one h1 (issue 829) */
  pageTitle?: boolean
}>()
</script>

<template>
  <div class="empty-state" role="status">
    <span v-if="icon" class="es-tile"><AppIcon :name="icon" :size="22" /></span>
    <component :is="pageTitle ? 'h1' : 'h2'" class="es-title">{{ title }}</component>
    <p v-if="hint" class="es-hint">{{ hint }}</p>
    <div v-if="$slots.default" class="es-actions"><slot /></div>
  </div>
</template>

<style scoped>
.empty-state {
  padding: 48px 24px;
  text-align: center;
  color: var(--soft);
}
.es-tile {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--r);
  background: var(--panel);
  border: 1px solid var(--line2);
  margin-bottom: 12px;
}
.es-title {
  color: var(--ink);
  margin: 0 0 6px;
}
.es-hint {
  margin: 0 auto;
  max-width: 62ch;
}
.es-actions {
  margin-top: 16px;
  display: flex;
  justify-content: center;
  gap: 10px;
}
</style>

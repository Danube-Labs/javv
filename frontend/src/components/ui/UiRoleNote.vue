<script setup lang="ts">
/**
 * The reason next to a control that the user's role cannot use: a key and one short sentence. The
 * control stays on the screen, disabled, and points at this note with `aria-describedby`, so a
 * keyboard or screen-reader user gets the reason too (a browser shows no tooltip on a disabled
 * button). Ruled on built pictures, issue 243. A control that a limit turns off, not a role,
 * gives another `icon`, so the key keeps meaning a permission.
 */
import AppIcon, { type IconName } from './AppIcon.vue'

withDefaults(defineProps<{ id: string; icon?: IconName }>(), { icon: 'key' })
</script>

<template>
  <span :id="id" class="ui-role-note"><AppIcon :name="icon" :size="13" /><slot /></span>
</template>

<style scoped>
.ui-role-note {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  color: var(--soft);
  white-space: nowrap;
}
.ui-role-note svg {
  flex: none;
  color: var(--hist-fg);
}
</style>

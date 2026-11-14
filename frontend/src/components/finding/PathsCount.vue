<script setup lang="ts">
/**
 * The cell of the Paths column (issue 1077): the number of paths of each finding of a row. When
 * a finding has a path to show, the cell is a button that opens the list under the row; the
 * parent owns the open state and the row that holds the list.
 */
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { countText, countTitle, type FindingPaths, hasPaths, openLabel } from '@/findings/paths'

defineProps<{
  entries: FindingPaths[]
  open: boolean
  /** the id of the element that lists the paths */
  controls: string
}>()

/* the row may open the finding on a click: the button keeps its click to itself */
const emit = defineEmits<{ toggle: [] }>()
</script>

<template>
  <UiButton
    v-if="hasPaths(entries)"
    class="paths-btn"
    :title="countTitle(entries)"
    :aria-label="openLabel(entries)"
    :aria-expanded="open"
    :aria-controls="controls"
    @click.stop="emit('toggle')"
  >
    {{ countText(entries) }}
    <AppIcon name="chevron" :size="11" class="paths-chev" :class="{ 'paths-chev--open': open }" />
  </UiButton>
  <span v-else-if="countText(entries) === '-'" class="muted-dash" :title="countTitle(entries)">-</span>
  <span v-else class="mono-cell sm paths-none" :title="countTitle(entries)">{{ countText(entries) }}</span>
</template>

<style scoped>
.paths-btn {
  font-family: var(--font-mono);
}
/* the chevron points down and turns up while open: the list opens here. A chevron that points
   right (`.cell-go`) says that a click opens another page */
.paths-chev {
  transform: rotate(90deg);
  transition: transform var(--dur-quick) var(--ease-out);
}
.paths-chev--open {
  transform: rotate(-90deg);
}
/* open: the hover state stays, as on the panel filters button of a dashboard */
.paths-btn[aria-expanded='true'] {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
@media (prefers-reduced-motion: reduce) {
  .paths-chev {
    transition: none;
  }
}
.paths-none {
  color: var(--soft);
}
</style>

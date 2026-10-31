<script setup lang="ts">
/**
 * The "N filters" button of a dashboard panel (issue 999, decision 2 C): over the top right
 * corner of the panel, next to the pinned scanner tag. A click opens the filters of the panel in
 * words, in a popover next to the panel, with a link to Findings with the same filters (the panel
 * filter popover of Kibana). A panel with no filters shows no button.
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import type { ViewPreset } from '@/api/generated'
import AppIcon from '@/components/ui/AppIcon.vue'
import PopoverShell from '@/components/ui/PopoverShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { panelFilterParts, panelFindingsQuery } from '@/dashboards/panelFilters'

const props = defineProps<{
  filters: ViewPreset | null | undefined
  panelName: string
  /** the scanner the panel is pinned to: Findings opens on it too */
  pinned?: 'trivy' | 'grype' | null
}>()

const router = useRouter()
const parts = computed(() => panelFilterParts(props.filters))
const label = computed(() => `${parts.value.length} ${parts.value.length === 1 ? 'filter' : 'filters'}`)

const open = ref<{ anchor: HTMLElement; trigger: HTMLElement } | null>(null)
function toggle(ev: MouseEvent) {
  if (open.value) {
    open.value = null
    return
  }
  const trigger = ev.currentTarget as HTMLElement
  // the popover sits next to the whole panel, as the panel settings do
  open.value = { anchor: trigger.closest<HTMLElement>('[data-panel]') ?? trigger, trigger }
}

function openFindings() {
  const row: Record<string, string> = props.pinned ? { scanner: props.pinned } : {}
  open.value = null
  void router.push({ path: '/findings', query: panelFindingsQuery(props.filters, row) })
}
</script>

<template>
  <template v-if="parts.length">
    <UiButton
      class="pf-btn"
      :aria-label="`${label} on ${panelName}`"
      aria-haspopup="dialog"
      :aria-expanded="open !== null"
      @click="toggle"
    >
      <AppIcon name="filter" :size="12" />{{ label }}
    </UiButton>
    <PopoverShell
      v-if="open"
      title="Panel filters"
      :subtitle="panelName"
      :anchor="open.anchor"
      :trigger="open.trigger"
      :width="320"
      @close="open = null"
    >
      <p class="pf-intro">The numbers of this panel count only these findings.</p>
      <ul class="pf-list">
        <li v-for="part in parts" :key="part" class="pf-item">{{ part }}</li>
      </ul>
      <div class="pf-actions">
        <UiButton variant="control" @click="openFindings">Open in Findings</UiButton>
      </div>
    </PopoverShell>
  </template>
</template>

<style scoped>
/* open: the hover state stays, so the button shows which panel the popover is for */
.pf-btn[aria-expanded='true'] {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.pf-intro {
  margin: 0 0 10px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.pf-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.pf-item {
  /* a label, not a control: the paper fill and no border (the soft badge of Nuxt UI) */
  padding: 2px 8px;
  background: var(--bg);
  border-radius: var(--r-chip);
  font-size: var(--text-sm);
  color: var(--ink);
}
.pf-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>

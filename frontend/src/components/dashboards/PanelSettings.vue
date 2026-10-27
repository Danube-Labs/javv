<script setup lang="ts">
/**
 * The settings of one panel in edit mode (issue 440, rulings Q6 and Q7), in a popover next to the
 * panel (option B, 2026-10-26), so the panel stays in view: the scanner for a panel with scanner
 * data, the width, and the height for a panel that has more than one. Apply changes the draft
 * only; the save bar saves it.
 */
import { ref } from 'vue'

import PopoverShell from '@/components/ui/PopoverShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { heightsOf, panelById, type PanelHeight } from '@/dashboards/catalog'
import {
  HEIGHT_OPTS,
  PANEL_SCANNER_OPTS,
  scannerHelp,
  WIDTH_OPTS,
  widthChoice,
  widthOf,
  type DraftPanel,
  type PanelScannerChoice,
  type PanelSettings,
  type WidthChoice,
} from '@/dashboards/edit'
import type { ScannerLens } from '@/lib/scannerLens'

const props = defineProps<{
  panel: DraftPanel
  dashboardScanner: ScannerLens
  anchor: HTMLElement
  trigger?: HTMLElement | null
}>()
const emit = defineEmits<{ close: []; apply: [settings: PanelSettings] }>()

const entry = panelById(props.panel.panel)
const heights = entry ? heightsOf(entry) : []
const w = ref<WidthChoice>(widthChoice(props.panel.w))
const h = ref<PanelHeight>(props.panel.h)
const scanner = ref<PanelScannerChoice>(props.panel.scanner ?? 'dashboard')

function apply() {
  emit('apply', { w: widthOf(w.value), h: h.value, scanner: entry?.usesScanner ? scanner.value : null })
}
</script>

<template>
  <PopoverShell
    title="Panel settings"
    :subtitle="entry?.name"
    :anchor="anchor"
    :trigger="trigger"
    :width="380"
    @close="emit('close')"
  >
    <div>
      <UiField v-if="entry?.usesScanner" label="Scanner" first>
        <UiSegControl v-model="scanner" :options="PANEL_SCANNER_OPTS" label="Scanner" />
        <p class="ps-help">{{ scannerHelp(scanner, dashboardScanner) }}</p>
      </UiField>
      <UiField label="Width" :first="!entry?.usesScanner">
        <UiSegControl v-model="w" :options="WIDTH_OPTS" label="Width" />
      </UiField>
      <UiField v-if="heights.length > 1" label="Height">
        <UiSegControl v-model="h" :options="HEIGHT_OPTS" label="Height" />
      </UiField>
      <div class="ps-actions">
        <UiButton variant="control" @click="emit('close')">Cancel</UiButton>
        <UiButton variant="primary" @click="apply">Apply</UiButton>
      </div>
    </div>
  </PopoverShell>
</template>

<style scoped>
.ps-help {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.ps-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
</style>

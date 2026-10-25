<script setup lang="ts">
/**
 * The settings of one panel in edit mode (issue 440, rulings Q6 and Q7), in the kit slide-over:
 * the scanner for a panel with scanner data, the width, and the height for a panel that has
 * more than one. Apply changes the draft only; the save bar saves it.
 */
import { ref } from 'vue'

import SlideoverShell from '@/components/ui/SlideoverShell.vue'
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

const props = defineProps<{ panel: DraftPanel; dashboardScanner: ScannerLens }>()
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
  <SlideoverShell title="Panel settings" :subtitle="entry?.name" :width="420" @close="emit('close')">
    <div class="ps">
      <p class="ps-line">{{ entry?.line }}</p>
      <UiField v-if="entry?.usesScanner" label="Scanner" first>
        <UiSegControl v-model="scanner" :options="PANEL_SCANNER_OPTS" />
        <p class="ps-help">{{ scannerHelp(scanner, dashboardScanner) }}</p>
      </UiField>
      <UiField label="Width" :first="!entry?.usesScanner">
        <UiSegControl v-model="w" :options="WIDTH_OPTS" />
      </UiField>
      <UiField v-if="heights.length > 1" label="Height">
        <UiSegControl v-model="h" :options="HEIGHT_OPTS" />
      </UiField>
      <div class="ps-actions">
        <UiButton variant="control" @click="emit('close')">Cancel</UiButton>
        <UiButton variant="primary" @click="apply">Apply</UiButton>
      </div>
    </div>
  </SlideoverShell>
</template>

<style scoped>
.ps {
  padding: 16px 18px 18px;
}
.ps-line {
  margin: 0 0 16px;
  font-size: var(--text-body);
  color: var(--ink);
}
.ps-help {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.ps-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 24px;
}
</style>

<script setup lang="ts">
/**
 * The catalog window of edit mode (issue 440, ruling Q1): the panels JAVV ships by group, one
 * line each, and for the chosen panel its settings and a preview with live data, at the width
 * and the height it will have on the dashboard.
 */
import { computed, ref } from 'vue'

import type { DashboardPanel } from '@/api/generated'
import PanelFrame from '@/components/dashboards/PanelFrame.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { heightsOf, PANELS, type PanelGroup, type PanelHeight } from '@/dashboards/catalog'
import {
  HEIGHT_OPTS,
  MAX_PANELS,
  PANEL_SCANNER_OPTS,
  scannerHelp,
  WIDTH_OPTS,
  widthChoice,
  widthOf,
  type PanelScannerChoice,
  type PanelSettings,
  type WidthChoice,
} from '@/dashboards/edit'
import { panelPropsCache, placeOne } from '@/dashboards/layout'
import type { ScannerLens } from '@/lib/scannerLens'

const props = defineProps<{
  count: number
  clusterId: string | null
  t: string | null
  windowDays: number
  dashboardScanner: ScannerLens
}>()
const emit = defineEmits<{ close: []; add: [choice: { panel: DashboardPanel['panel'] } & PanelSettings] }>()

const GROUPS: PanelGroup[] = ['Findings', 'Scanners', 'People']

const picked = ref(PANELS[0]!)
const w = ref<WidthChoice>(widthChoice(picked.value.defaultWidth))
const h = ref<PanelHeight>(heightsOf(picked.value)[0]!)
const scanner = ref<PanelScannerChoice>('dashboard')

function pick(id: string) {
  const entry = PANELS.find((p) => p.id === id)
  if (!entry) return
  picked.value = entry
  w.value = widthChoice(entry.defaultWidth)
  h.value = heightsOf(entry)[0]!
  scanner.value = 'dashboard'
}

const choice = computed(() => ({
  panel: picked.value.id as DashboardPanel['panel'],
  w: widthOf(w.value),
  h: h.value,
  scanner: picked.value.usesScanner ? scanner.value : null,
}))

const preview = computed(() => placeOne({ ...choice.value, x: 0, y: 0, scanner: choice.value.scanner ?? undefined }))
const propsFor = panelPropsCache()
const previewProps = computed(() =>
  preview.value && props.clusterId
    ? propsFor('preview', preview.value, { ...props, clusterId: props.clusterId, scanner: props.dashboardScanner })
    : {},
)
</script>

<template>
  <ModalShell
    title="Add a panel"
    :subtitle="`The panels that JAVV ships. This dashboard has ${count} of ${MAX_PANELS}.`"
    :width="1080"
    @close="emit('close')"
  >
    <div class="cat">
      <nav class="cat-list" aria-label="Panels">
        <template v-for="g in GROUPS" :key="g">
          <p class="cat-group">{{ g }}</p>
          <button
            v-for="p in PANELS.filter((c) => c.group === g)"
            :key="p.id"
            type="button"
            class="cat-row"
            :class="{ 'cat-row-on': p.id === picked.id }"
            :aria-pressed="p.id === picked.id"
            :data-panel="p.id"
            @click="pick(p.id)"
          >
            <span class="cat-name">{{ p.name }}</span>
            <span class="cat-line">{{ p.line }}</span>
          </button>
        </template>
      </nav>
      <section class="cat-detail">
        <h4>{{ picked.name }}</h4>
        <p class="cat-desc">{{ picked.line }}</p>
        <div class="cat-opts">
          <UiField v-if="picked.usesScanner" label="Scanner" first>
            <UiSegControl v-model="scanner" :options="PANEL_SCANNER_OPTS" label="Scanner" />
          </UiField>
          <UiField label="Width" first>
            <UiSegControl v-model="w" :options="WIDTH_OPTS" label="Width" />
          </UiField>
          <UiField v-if="heightsOf(picked).length > 1" label="Height" first>
            <UiSegControl v-model="h" :options="HEIGHT_OPTS" label="Height" />
          </UiField>
        </div>
        <p v-if="picked.usesScanner" class="cat-help">{{ scannerHelp(scanner, dashboardScanner) }}</p>
        <p class="cat-prev-label">Preview with live data</p>
        <p v-if="!clusterId" class="cat-help">Select a cluster at the top of the page to see the preview.</p>
        <div
          v-else-if="preview"
          class="cat-prev"
          :class="{ 'cat-prev-half': w === 'half' }"
          :style="{ height: `${preview.rows * 40 - 30}px` }"
        >
          <PanelFrame v-if="picked.framed" :title="picked.name" :line="picked.line">
            <component :is="picked.component" :key="picked.id" v-bind="previewProps" />
          </PanelFrame>
          <component :is="picked.component" v-else :key="picked.id" v-bind="previewProps" />
        </div>
      </section>
    </div>
    <template #actions>
      <UiButton variant="control" @click="emit('close')">Cancel</UiButton>
      <UiButton variant="primary" @click="emit('add', choice)">Add panel</UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.cat {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 18px;
  min-height: 560px;
  padding: 4px 16px 8px;
}
.cat-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-right: 14px;
  border-right: 1px solid var(--line2);
  overflow: auto;
}
.cat-group {
  margin: 10px 0 2px;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink);
}
.cat-group:first-child {
  margin-top: 0;
}
.cat-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px;
  text-align: left;
  font-family: var(--font-ui);
  color: var(--ink);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  transition:
    background var(--dur-quick) var(--ease-out),
    border-color var(--dur-quick) var(--ease-out);
}
.cat-row:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.cat-row:active {
  background: var(--control-active-bg);
}
.cat-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
/* the selection language of an overlay (DESIGN.md §2) */
.cat-row-on,
.cat-row-on:hover {
  background: var(--dd-on-bg);
  border-color: transparent;
  box-shadow: inset 2px 0 0 var(--coral);
}
.cat-name {
  font-size: var(--text-body);
  font-weight: 600;
}
.cat-line {
  font-size: var(--text-sm);
  color: var(--soft);
}
.cat-detail {
  min-width: 0;
}
.cat-detail h4 {
  margin: 0;
  font-size: var(--text-card-title);
  font-weight: 600;
}
.cat-desc {
  margin: 4px 0 12px;
  font-size: var(--text-body);
  color: var(--ink);
}
.cat-opts {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 22px;
}
.cat-help {
  margin: 8px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.cat-prev-label {
  margin: 16px 0 12px;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--soft);
}
/* the slot the panel gets on the dashboard; a panel taller than it scrolls, as there */
.cat-prev {
  overflow: auto;
}
.cat-prev-half {
  width: calc(50% - 15px);
}
</style>

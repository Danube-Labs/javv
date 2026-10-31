<script setup lang="ts">
/**
 * The settings of one panel in edit mode (issue 440, rulings Q6 and Q7), in a popover next to the
 * panel (option B, 2026-10-26), so the panel stays in view: the scanner for a panel with scanner
 * data, the width, the height for a panel that has more than one, and the findings filters for a
 * panel that counts findings (issue 999, decision 3 B: the Findings filter bar). Apply changes the
 * draft only; the save bar saves it.
 */
import { computed, ref } from 'vue'

import FilterBar from '@/components/filters/FilterBar.vue'
import PopoverShell from '@/components/ui/PopoverShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { useFindingsFacets } from '@/composables/useFindingsFacets'
import { findingsValueSearch } from '@/composables/useValueSearch'
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
import { countedScanner } from '@/dashboards/layout'
import { panelFilterFields } from '@/dashboards/panelFilters'
import { FINDINGS_EXCLUSIVE_PAIRS, FINDINGS_FIELDS, MAX_FILTER_VALUES } from '@/filters/fields.config'
import { captureLens, presetToRouteQuery } from '@/findings/savedViews'
import type { ScannerLens } from '@/lib/scannerLens'
import { makeFiltersStore } from '@/stores/filters'

const props = defineProps<{
  panel: DraftPanel
  dashboardScanner: ScannerLens
  anchor: HTMLElement
  trigger?: HTMLElement | null
  /** the dashboard's cluster, T and range: the counts of the Add filter menu */
  clusterId: string | null
  t: string | null
  windowDays: number
}>()
const emit = defineEmits<{ close: []; apply: [settings: PanelSettings] }>()

const entry = panelById(props.panel.panel)
const heights = entry ? heightsOf(entry) : []
const w = ref<WidthChoice>(widthChoice(props.panel.w))
const h = ref<PanelHeight>(props.panel.h)
const scanner = ref<PanelScannerChoice>(props.panel.scanner ?? 'dashboard')

const fields = entry?.takesFilters ? panelFilterFields(entry) : []
const filters = useSettingsFilters()
filters.fromQuery(props.panel.filters ? presetToRouteQuery(FINDINGS_FIELDS, props.panel.filters) : {})
const draftFilters = computed(() => captureLens(fields, filters.selections, filters.modes, props.windowDays))

const countScanner = computed(() =>
  entry ? countedScanner(entry, { scanner: scanner.value }, props.dashboardScanner) : 'all',
)

// the Findings rule for the menu: a field does not count under its own filter, so the values not
// picked yet stay in the list. The panel itself reads with all_filters.
const menuQuery = () =>
  fields.length && props.clusterId
    ? {
        cluster_id: props.clusterId,
        ...(props.t ? { as_of: props.t } : {}),
        ...(countScanner.value !== 'all' ? { scanner: countScanner.value } : {}),
        ...draftFilters.value,
      }
    : null
const { facets, failed } = useFindingsFacets(() => undefined, menuQuery)
// a value past the top 32: the menu asks under the same query (issue 1064)
const searchValues = findingsValueSearch(menuQuery)

function apply() {
  const settings: PanelSettings = { w: widthOf(w.value), h: h.value, scanner: entry?.usesScanner ? scanner.value : null }
  if (fields.length) settings.filters = Object.keys(draftFilters.value).length ? draftFilters.value : null
  emit('apply', settings)
}
</script>

<script lang="ts">
// one store for the popover: it holds every field a panel can filter on, and each panel shows its own
const useSettingsFilters = makeFiltersStore(
  'panel-settings-filters',
  FINDINGS_FIELDS.filter((f) => f.key !== 'scanner'),
  MAX_FILTER_VALUES,
  FINDINGS_EXCLUSIVE_PAIRS,
)
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
      <UiField v-if="fields.length" label="Filters">
        <FilterBar
          :fields="fields"
          :selections="filters.selections"
          :modes="filters.modes"
          :facets="facets"
          :counts-unknown="failed"
          :max-values="MAX_FILTER_VALUES"
          :search-values="searchValues"
          menu-up
          @toggle="filters.toggle"
          @set-text="filters.setText"
          @set-mode="filters.setMode"
          @toggle-mode="filters.toggleMode"
          @clear-field="filters.clearField"
          @clear-all="filters.clearAll"
        />
        <p class="ps-help">The panel counts only the findings that match these filters.</p>
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

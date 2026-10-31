<script setup lang="ts">
/**
 * Discover-style filter bar (prototype filters.jsx `FilterBar` + `.fpill`/`.add-filter`/`.dd-menu`
 * CSS): active-filter pills, a two-level add-filter dropdown (field list → value picker, with a
 * value search above 8 entries; text fields get an input), clear-all. Keyboard: Esc closes,
 * arrows walk the menu. Lists values through the same `facetItems()` the FacetRail uses — one
 * config drives both.
 */
import { computed, ref, useTemplateRef } from 'vue'

import FilterPill from '@/components/filters/FilterPill.vue'
import FilterValueRows, { type ValueRow } from '@/components/filters/FilterValueRows.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiDropdown from '@/components/ui/UiDropdown.vue'
import UiSearchBox from '@/components/ui/UiSearchBox.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { facetItems, type FacetsResponse } from '@/filters/facets'
import { isNegatable, type FilterField, type Selections } from '@/filters/fields.config'
import { inText, typedValuesToAdd } from '@/filters/typedValues'
import type { FilterMode, Modes } from '@/stores/filters'

const props = defineProps<{
  fields: readonly FilterField[]
  selections: Selections
  modes?: Modes
  facets: FacetsResponse
  /** the counts read was refused: the menu shows no count (issue 833, F9) */
  countsUnknown?: boolean
  /** the most values one field takes, where the API caps it (Findings, issue 949) */
  maxValues?: number
  /** the menu opens above the bar: in the settings popover of a dashboard panel (issue 999) */
  menuUp?: boolean
}>()

const emit = defineEmits<{
  toggle: [fieldKey: string, value: string]
  setText: [fieldKey: string, value: string]
  setMode: [fieldKey: string, mode: FilterMode]
  toggleMode: [fieldKey: string]
  clearField: [fieldKey: string]
  clearAll: []
}>()

const MODE_OPTIONS = [
  { value: 'is', label: 'is' },
  { value: 'not', label: 'is not' },
] as const

function modeOf(fieldKey: string): FilterMode {
  return props.modes?.[fieldKey] ?? 'is'
}
const negatable = isNegatable

const open = ref(false)
const editKey = ref<string | null>(null)
const valueQuery = ref('')
const textDraft = ref('')
const wrap = useTemplateRef<HTMLElement>('wrap')

const active = computed(() => props.fields.filter((f) => (props.selections[f.key] ?? []).length > 0))
const editField = computed(() => props.fields.find((f) => f.key === editKey.value) ?? null)
const editItems = computed(() => {
  const field = editField.value
  if (!field) return null
  const items = facetItems(field, props.facets, props.selections[field.key])
  if (!items) return null
  const q = valueQuery.value.toLowerCase()
  // match the name on screen AND the stored value: someone who knows `not_affected` from a
  // URL or the API finds it too
  const chosen = props.selections[field.key] ?? []
  const shown = q ? items.filter((it) => it.label.toLowerCase().includes(q) || it.value.toLowerCase().includes(q)) : items
  return shown.map((it): ValueRow => ({ ...it, on: chosen.includes(it.value) }))
})
// several typed values (issue 949): the field's values listed under its input
const typedRows = computed((): ValueRow[] => {
  const field = editField.value
  if (!field || !isMultiText(field)) return []
  return (props.selections[field.key] ?? []).map((v) => ({ value: v, label: v, on: true, count: null }))
})

function isMultiText(field: FilterField): boolean {
  return field.type === 'text' && field.multi === true
}
const atCap = computed(
  () => props.maxValues !== undefined && (props.selections[editKey.value ?? ''] ?? []).length >= props.maxValues,
)

function openPicker() {
  editKey.value = null
  valueQuery.value = ''
  open.value = true
}
function openField(key: string) {
  editKey.value = key
  valueQuery.value = ''
  const field = props.fields.find((f) => f.key === key)
  // a multi text field lists its values under the input, so the input starts empty
  textDraft.value = field && isMultiText(field) ? '' : ((props.selections[key] ?? [])[0] ?? '')
  open.value = true
}
function close() {
  open.value = false
}
// UiDropdown owns outside-click/Escape closing — reset the two-level editor on ANY close
// path, but only after the leave fade so the panel doesn't swap content mid-fade
function onClosed() {
  editKey.value = null
}

function applyText() {
  const field = editField.value
  if (!field) return
  if (isMultiText(field)) {
    // each Enter adds and keeps the box open for the next (issue 949)
    // a value past the cap stays in the input, so a long pasted list loses nothing
    const { add, left } = typedValuesToAdd(textDraft.value, props.selections[field.key] ?? [], props.maxValues)
    for (const v of add) emit('toggle', field.key, v)
    textDraft.value = left.join(', ')
    return
  }
  emit('setText', field.key, textDraft.value)
  close()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    // an open menu takes this Escape, so a popover or a window around the bar stays open
    if (open.value) e.stopPropagation()
    close()
    return
  }
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    const menu = wrap.value?.querySelector('.dd-menu')
    if (!menu) return
    e.preventDefault()
    const items = [...menu.querySelectorAll('button')]
    const idx = items.indexOf(document.activeElement as HTMLButtonElement)
    const next = e.key === 'ArrowDown' ? Math.min(idx + 1, items.length - 1) : Math.max(idx - 1, 0)
    items[next]?.focus()
  }
}

</script>

<template>
  <div ref="wrap" class="filter-bar" @keydown="onKeydown">
    <FilterPill
      v-for="f in active"
      :key="f.key"
      :field="f"
      :values="selections[f.key] ?? []"
      :mode="modeOf(f.key)"
      @open="openField(f.key)"
      @toggle-mode="emit('toggleMode', f.key)"
      @clear="emit('clearField', f.key)"
    />

    <UiDropdown v-model:open="open" @closed="onClosed">
      <template #trigger>
        <button class="add-filter" @click="open ? close() : openPicker()">
          <AppIcon name="plus" :size="13" />Add filter
        </button>
      </template>
      <div class="dd-menu filter-menu" :class="{ 'dd-menu--up': menuUp }">
        <template v-if="!editField">
          <div class="dd-head">Filter by field</div>
          <button
            v-for="f in fields"
            :key="f.key"
            class="dd-item filter-field"
            @click="openField(f.key)"
          >
            <span>{{ f.label }}</span>
            <span v-if="(selections[f.key] ?? []).length > 0" class="field-badge">
              {{ (selections[f.key] ?? []).length }}
            </span>
            <AppIcon name="chevron" :size="13" />
          </button>
        </template>

        <template v-else>
          <button class="filter-back" @click="editKey = null">
            <AppIcon name="arrowback" :size="13" />{{ editField.label }}
          </button>

          <div v-if="negatable(editField)" class="filter-mode">
            <UiSegControl
              :options="MODE_OPTIONS"
              :label="editField.label"
              :model-value="modeOf(editField.key)"
              @update:model-value="(m) => emit('setMode', editField!.key, m)"
            />
          </div>

          <template v-if="editItems">
            <UiSearchBox
              v-if="editItems.length > 8 || valueQuery"
              v-model="valueQuery"
              class="filter-vsearch"
              placeholder="Filter values…"
            />
            <FilterValueRows
              :rows="editItems"
              :counts-unknown="countsUnknown"
              @toggle="(v) => emit('toggle', editField!.key, v)"
            />
          </template>

          <template v-else>
            <UiSearchBox
              v-model="textDraft"
              class="filter-vsearch"
              :placeholder="isMultiText(editField) ? `Add ${inText(editField.label)}…` : `${editField.label}…`"
              @keydown.enter="applyText"
            />
            <FilterValueRows
              v-if="typedRows.length > 0"
              :rows="typedRows"
              removable
              @toggle="(v) => emit('toggle', editField!.key, v)"
            />
          </template>

          <p v-if="atCap" class="filter-note" role="status">
            A filter takes at most {{ maxValues }} values.
          </p>
          <button
            v-if="(selections[editField.key] ?? []).length > 0"
            class="filter-clear-field"
            @click="emit('clearField', editField.key)"
          >
            Clear {{ inText(editField.label) }}
          </button>
        </template>
      </div>
    </UiDropdown>

    <button v-if="active.length > 0" class="clear-all" @click="emit('clearAll')">Clear all</button>
    <slot name="extra" />
  </div>
</template>

<style scoped>
.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.add-filter:focus-visible,
.dd-item:focus-visible,
.clear-all:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.filter-mode {
  padding: 8px 10px 2px;
}
.add-filter {
  display: inline-flex;
  flex: none;
  align-items: center;
  white-space: nowrap;
  gap: 6px;
  height: 38px; /* same register as .fpill in FilterPill.vue */
  border: 1px dashed var(--add-filter-line);
  background: var(--card);
  color: var(--ink);
  border-radius: var(--r-sm);
  padding: 0 12px;
  font-size: var(--text-control);
  font-weight: 500;
  cursor: default;
}
.add-filter:hover {
  border-color: var(--coral);
  color: var(--coral-text);
  background: var(--add-filter-hover-bg);
}
.clear-all {
  border: 0;
  background: transparent;
  color: var(--soft);
  font-size: var(--text-quiet-action);
  text-decoration: underline;
  text-underline-offset: 2px;
  padding: 4px;
  cursor: default;
}
.clear-all:hover {
  color: var(--coral-text);
}
.dd-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 30;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--dd-shadow);
  padding: 6px;
  min-width: 230px;
}
.filter-menu {
  min-width: 248px;
  max-width: 280px;
}
.dd-menu--up {
  top: auto;
  bottom: calc(100% + 6px);
}
.dd-head {
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--soft);
  padding: 8px 12px 6px;
}
.dd-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  text-align: left;
  color: var(--ink);
  font-size: var(--text-dd-item);
  cursor: default;
}
.dd-item:hover {
  background: var(--panel);
}
.filter-field {
  justify-content: space-between;
}
.filter-field > span:first-child {
  flex: 1;
}
.field-badge {
  background: var(--coral);
  color: var(--kev-fg);
  font-size: var(--text-facet-label);
  font-weight: 700;
  font-family: var(--font-mono);
  min-width: 17px;
  height: 17px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  padding: 0 5px;
}
.filter-back {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-weight: 600;
  font-size: var(--text-dd-item);
  padding: 7px 9px;
  border-bottom: 1px solid var(--line2);
  margin-bottom: 4px;
  cursor: default;
}
.filter-back:hover {
  color: var(--coral-text);
}
.filter-back svg {
  color: var(--soft);
}
.filter-vsearch {
  margin: 0 4px 6px;
  padding: 6px 9px;
}
.filter-note {
  margin: 0 8px 6px;
  font-size: var(--text-quiet-action);
  color: var(--soft);
}
.filter-clear-field {
  width: 100%;
  border: 0;
  border-top: 1px solid var(--line2);
  background: transparent;
  color: var(--soft);
  font-size: var(--text-quiet-action);
  padding: 8px;
  margin-top: 4px;
  cursor: default;
}
.filter-clear-field:hover {
  color: var(--coral-text);
}
</style>

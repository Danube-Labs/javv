<script setup lang="ts">
/**
 * Discover-style filter bar (prototype filters.jsx `FilterBar` + `.fpill`/`.add-filter`/`.dd-menu`
 * CSS): active-filter pills, a two-level add-filter dropdown (field list → value picker, with a
 * value search above 8 entries; text fields get an input), clear-all. Keyboard: Esc closes,
 * arrows walk the menu. Lists values through the same `facetItems()` the FacetRail uses — one
 * config drives both.
 */
import { computed, ref, useTemplateRef } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import UiDropdown from '@/components/ui/UiDropdown.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import { facetItems, type FacetsResponse } from '@/filters/facets'
import { isNegatable, valueLabel, type FilterField, type Selections } from '@/filters/fields.config'
import type { FilterMode, Modes } from '@/stores/filters'

const props = defineProps<{
  fields: readonly FilterField[]
  selections: Selections
  modes?: Modes
  facets: FacetsResponse
  /** the counts read was refused: the menu shows no count (issue 833, F9) */
  countsUnknown?: boolean
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
function opText(field: FilterField): string {
  const many = (props.selections[field.key] ?? []).length > 1
  return modeOf(field.key) === 'not' ? (many ? 'is none of' : 'is not') : many ? 'is one of' : 'is'
}

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
  return q ? items.filter((it) => it.label.toLowerCase().includes(q) || it.value.toLowerCase().includes(q)) : items
})

function pillText(field: FilterField): string {
  const vals = (props.selections[field.key] ?? []).map((v) => valueLabel(field, v))
  return vals.length <= 2 ? vals.join(', ') : `${vals.slice(0, 2).join(', ')} +${vals.length - 2}`
}

function openPicker() {
  editKey.value = null
  valueQuery.value = ''
  open.value = true
}
function openField(key: string) {
  editKey.value = key
  valueQuery.value = ''
  textDraft.value = (props.selections[key] ?? [])[0] ?? ''
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
  if (!editField.value) return
  emit('setText', editField.value.key, textDraft.value)
  close()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
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
    <button
      v-for="f in active"
      :key="f.key"
      class="fpill"
      :class="{ 'fpill-not': modeOf(f.key) === 'not' }"
      @click="openField(f.key)"
    >
      <span class="fpill-field">{{ f.label }}</span>
      <!-- ruled NOT-pill (issue 349, operator 2026-07-17): hollow body, ONLY the op words in
           red; on a negatable field the op word is the include⇄exclude toggle -->
      <span
        v-if="negatable(f)"
        class="fpill-op fpill-op-btn"
        role="button"
        :aria-label="`Switch to ${modeOf(f.key) === 'not' ? 'include' : 'exclude'}`"
        :title="modeOf(f.key) === 'not' ? 'Click to include' : 'Click to exclude'"
        @click.stop="emit('toggleMode', f.key)"
        >{{ opText(f) }}</span
      >
      <span v-else class="fpill-op">{{ opText(f) }}</span>
      <span class="fpill-vals">{{ pillText(f) }}</span>
      <span
        class="fpill-x"
        role="button"
        :aria-label="`Clear ${f.label}`"
        @click.stop="emit('clearField', f.key)"
        >×</span
      >
    </button>

    <UiDropdown v-model:open="open" @closed="onClosed">
      <template #trigger>
        <button class="add-filter" @click="open ? close() : openPicker()">
          <AppIcon name="plus" :size="13" />Add filter
        </button>
      </template>
      <div class="dd-menu filter-menu">
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
              :model-value="modeOf(editField.key)"
              @update:model-value="(m) => emit('setMode', editField!.key, m)"
            />
          </div>

          <template v-if="editItems">
            <div v-if="editItems.length > 8 || valueQuery" class="filter-vsearch">
              <AppIcon name="search" :size="13" />
              <input v-model="valueQuery" placeholder="Filter values…" />
            </div>
            <div class="filter-values">
              <button
                v-for="it in editItems"
                :key="it.value"
                class="facet-row"
                :class="{ 'facet-on': (selections[editField.key] ?? []).includes(it.value) }"
                @click="emit('toggle', editField.key, it.value)"
              >
                <span class="facet-check" />
                <span class="facet-label">{{ it.label }}</span>
                <span v-if="it.count !== null" class="facet-count">{{
                  countsUnknown ? '-' : it.count.toLocaleString('en-US')
                }}</span>
              </button>
            </div>
          </template>

          <div v-else class="filter-vsearch">
            <AppIcon name="search" :size="13" />
            <input
              v-model="textDraft"
              :placeholder="`${editField.label}…`"
              @keydown.enter="applyText"
            />
          </div>

          <button
            v-if="(selections[editField.key] ?? []).length > 0"
            class="filter-clear-field"
            @click="emit('clearField', editField.key)"
          >
            Clear {{ editField.label.toLowerCase() }}
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
.fpill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  /* control register (operator, 2026-07-17): the band's controls share one height — the
     28px pills read as undersized next to every neighboring control */
  height: 38px;
  background: var(--card);
  border: 1px solid var(--fpill-line);
  border-radius: var(--r-sm);
  padding: 0 6px 0 10px;
  font-size: var(--text-control);
  color: var(--ink);
  box-shadow: var(--shadow);
  cursor: default;
}
.fpill:hover {
  border-color: var(--coral);
}
.fpill:focus-visible,
.add-filter:focus-visible,
.facet-row:focus-visible,
.dd-item:focus-visible,
.clear-all:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.fpill-field {
  font-weight: 600;
}
.fpill-op {
  color: var(--soft);
  font-style: italic;
  font-size: var(--text-sm);
}
.fpill-vals {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--coral-text);
  max-width: 230px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fpill-x {
  display: grid;
  place-items: center;
  width: 17px;
  height: 17px;
  border-radius: 5px;
  color: var(--soft);
  font-size: var(--text-card-title);
  line-height: 1;
}
.fpill-x:hover {
  background: var(--fpill-x-hover-bg);
  color: var(--coral-text);
}
/* the NOT-pill (issue 349, ruled 2026-07-17 on built specimens): the include pill is FILLED
   (card on beige), the exclude pill is HOLLOW — fill/outline duality — and ONLY the op words
   carry the red; the rest of the pill stays in the quiet register */
.fpill-not {
  background: transparent;
  border: 1.5px solid var(--fpill-line);
  box-shadow: none;
}
.fpill-not .fpill-op {
  color: var(--fpill-not-op);
  font-weight: 600;
}
/* the op word doubles as the include⇄exclude toggle on negatable fields */
.fpill-op-btn {
  border-radius: 4px;
  padding: 1px 3px;
  margin: -1px -3px;
}
.fpill-op-btn:hover {
  background: var(--fpill-x-hover-bg);
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
  height: 38px; /* same register as .fpill — see above */
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
  display: flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--line);
  border-radius: 7px;
  padding: 6px 9px;
  margin: 0 4px 6px;
  color: var(--soft);
}
.filter-vsearch input {
  border: 0;
  background: transparent;
  outline: none;
  flex: 1;
  font-size: var(--text-control);
  color: var(--ink);
  font-family: inherit;
}
.filter-values {
  max-height: 240px;
  overflow-y: auto;
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

/* value rows inside the picker (same look as the rail's facet rows) */
.facet-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  padding: 5px 8px;
  border-radius: 7px;
  text-align: left;
  color: var(--ink);
  font-size: var(--text-control);
  cursor: default;
}
.facet-row:hover {
  background: var(--panel);
}
.facet-check {
  width: 14px;
  height: 14px;
  border-radius: 4px;
  border: 1.5px solid var(--facet-check-line);
  flex: none;
  transition: 0.1s;
}
.facet-on .facet-check {
  background: var(--coral);
  border-color: var(--coral);
  box-shadow: inset 0 0 0 2px var(--card);
}
.facet-on {
  color: var(--ink);
  font-weight: 500;
}
.facet-label {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.facet-count {
  font-family: var(--font-mono);
  font-size: var(--text-facet-count);
  color: var(--soft);
}
</style>

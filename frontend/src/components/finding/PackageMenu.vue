<script setup lang="ts">
/**
 * The package menu of a finding's head band (issue 1205, S1 with the dark blue head: the operator
 * chose it on 2026-11-16 on built pictures, in place of the panel M1). The package name opens a
 * panel on the kit dropdown with each package and version of this CVE on this image, the
 * scanners that found it, and the current one in the coral language of a selection. The list
 * stops at about nine rows and scrolls (DESIGN.md §2, no unbounded panels). A filter box shows for
 * more than FILTER_FROM packages, as GitHub's SelectPanel and the Nuxt UI SelectMenu filter a long
 * list. The panel holds a form field, so it is a dialog and not a menu (Primer: no form field in a
 * menu).
 */
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiCloseButton from '@/components/ui/UiCloseButton.vue'
import UiDropdown from '@/components/ui/UiDropdown.vue'
import UiSearchBox from '@/components/ui/UiSearchBox.vue'
import type { PackageOnImage } from '@/findings/detailViewModel'
import type { FindingRow } from '@/stores/findings'

const props = defineProps<{
  packages: PackageOnImage[]
  /** the image has more findings of this CVE than the read holds */
  packagesCut: boolean
  /** the finding of the page: its package is the current one */
  primary: FindingRow | null
}>()

const route = useRoute()
const FILTER_FROM = 8
const pkOpen = ref(false)
const pkBtn = ref<HTMLElement | null>(null)
const pkMenu = ref<HTMLElement | null>(null)
const pkQuery = ref('')
const imageName = computed(() =>
  props.primary?.image_repo ? props.primary.image_repo + (props.primary.tag ? ':' + props.primary.tag : '') : undefined,
)
const shownPackages = computed(() => {
  const q = pkQuery.value.trim().toLowerCase()
  return q ? props.packages.filter((p) => p.name.toLowerCase().includes(q)) : props.packages
})
const isCurrent = (p: PackageOnImage) =>
  p.name === props.primary?.package_name && p.version === (props.primary?.installed_version ?? null)
/* the focus goes into the menu on open: the filter box, else the first link (Primer SelectPanel),
   and the list scrolls to the current package, which can be low in a long list. On a close, the
   focus goes back to the button when it is nowhere or still in the menu: the menu stays in the
   page for its leave motion, and the page body got the focus after it (issue 1229) */
watch(pkOpen, async (now) => {
  const menu = pkMenu.value
  await nextTick()
  if (now) {
    pkMenu.value?.querySelector<HTMLElement>('.pk-row.on')?.scrollIntoView({ block: 'nearest' })
    pkMenu.value?.querySelector<HTMLElement>('.search-box input, a.pk-row')?.focus({ preventScroll: true })
  } else {
    pkQuery.value = ''
    const at = document.activeElement
    if (!at || at === document.body || menu?.contains(at)) pkBtn.value?.focus()
  }
})
/** ArrowDown and ArrowUp move the focus through the filter box and the links */
function moveFocus(e: KeyboardEvent) {
  if ((e.key !== 'ArrowDown' && e.key !== 'ArrowUp') || !pkMenu.value) return
  const items = [...pkMenu.value.querySelectorAll<HTMLElement>('.search-box input, a.pk-row')]
  const at = items.indexOf(document.activeElement as HTMLElement)
  const next = e.key === 'ArrowDown' ? Math.min(at + 1, items.length - 1) : Math.max(at - 1, 0)
  items[next]?.focus()
  e.preventDefault()
}
</script>

<template>
  <UiDropdown v-model:open="pkOpen" class="pk-dd">
    <template #trigger="{ toggle, open }">
      <button
        ref="pkBtn"
        type="button"
        class="pk-btn"
        :title="primary?.package_name"
        :aria-expanded="open"
        aria-haspopup="dialog"
        @click="toggle"
      >
        <span class="mono-cell pk-btn-name">{{ primary?.package_name }}</span>
        <span class="pk-count">{{ packages.length }}{{ packagesCut ? '+' : '' }} on this image</span>
        <AppIcon name="chevron" :size="13" class="pk-chev" :class="{ open }" />
      </button>
    </template>
    <template #default="{ close }">
      <div ref="pkMenu" class="dd-menu pk-menu" role="dialog" aria-label="Packages with this vulnerability" @keydown="moveFocus">
        <div class="pk-head">
          <div class="pk-head-text">
            <span class="pk-title">Packages with this vulnerability · {{ packages.length }}{{ packagesCut ? '+' : '' }}</span>
            <span class="pk-img mono-cell">{{ imageName }}</span>
          </div>
          <UiCloseButton dark label="Close" @click="close()" />
        </div>
        <UiSearchBox
          v-if="packages.length > FILTER_FROM"
          v-model="pkQuery"
          class="pk-search"
          placeholder="Filter packages"
          aria-label="Filter packages"
        />
        <div class="pk-list">
          <template v-for="p in shownPackages" :key="`${p.name}|${p.version}`">
            <span v-if="isCurrent(p)" class="pk-row on" aria-current="true">
              <AppIcon name="check" :size="13" class="pk-mark" />
              <span class="pk-name mono-cell" :title="p.name">{{ p.name }}</span>
              <span class="pk-ver mono-cell">{{ p.version }}</span>
              <span class="pk-scn"><ScannerTag v-for="sc in p.scanners" :key="sc" :name="sc" /></span>
            </span>
            <RouterLink
              v-else
              class="pk-row"
              :to="{ query: { ...route.query, pkg: p.name, ver: p.version ?? undefined } }"
              @click="close()"
            >
              <span class="pk-mark" />
              <span class="pk-name mono-cell" :title="p.name">{{ p.name }}</span>
              <span class="pk-ver mono-cell">{{ p.version }}</span>
              <span class="pk-scn"><ScannerTag v-for="sc in p.scanners" :key="sc" :name="sc" /></span>
            </RouterLink>
          </template>
          <p v-if="!shownPackages.length" class="empty-note pk-note">No package matches.</p>
        </div>
        <p v-if="packagesCut" class="cap-note pk-note">This menu shows {{ packages.length }} packages. The image has more.</p>
      </div>
    </template>
  </UiDropdown>
</template>

<style scoped>
.pk-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  /* the negative margin lines the name up with its label, so the button may be 8px wider */
  max-width: calc(100% + 8px);
  height: 30px;
  margin-left: -8px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: var(--r-chip);
  background: none;
  color: var(--ink);
  font-size: var(--text-body);
}
.pk-btn:hover,
.pk-btn[aria-expanded='true'] {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.pk-btn:active {
  background: var(--control-active-bg);
}
.pk-btn:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
/* a long name takes the free space and ends with an ellipsis; the count and the chevron keep
   one line (issue 1229, operator ruling B1 of 2026-11-16 on built pictures) */
.pk-btn-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pk-count {
  flex: none;
  white-space: nowrap;
  padding: 1px 7px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--panel);
  color: var(--ink);
  font-size: var(--text-facet-label);
  font-weight: 600;
}
.pk-chev {
  flex: none;
  color: var(--soft);
  transform: rotate(90deg);
  transition: transform 0.12s;
}
.pk-chev.open {
  transform: rotate(-90deg);
}
.pk-dd {
  display: inline-block;
  max-width: 100%;
}
/* the menu: the list stops at about nine rows and scrolls (DESIGN.md §2, no unbounded panels) */
.pk-menu {
  left: -8px;
  width: 420px;
  border-radius: var(--r-sm);
  overflow: hidden;
}
/* the dark blue head of a window (ModalShell, PopoverShell band), operator 2026-11-16 */
.pk-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 10px 10px 14px;
  background: var(--table-head-bg);
  color: var(--table-head-fg);
}
.pk-head-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.pk-title {
  font-size: var(--text-card-title);
  font-weight: 600;
}
.pk-img {
  font-size: var(--text-sm);
  opacity: 0.75;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pk-search {
  margin: 8px 8px 2px;
}
.pk-list {
  display: flex;
  flex-direction: column;
  max-height: 296px;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 6px;
}
.pk-row {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: var(--r-chip);
  color: var(--ink);
  text-decoration: none;
  font-size: var(--text-dd-item);
}
a.pk-row:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
a.pk-row:active {
  background: var(--control-active-bg);
}
a.pk-row:focus-visible {
  outline: var(--focus-ring);
  outline-offset: -2px;
}
/* the current package wears the coral language of a selection in an overlay (DESIGN.md §2) */
.pk-row.on {
  background: var(--dd-on-bg);
  box-shadow: inset 0 0 0 1px var(--coral);
  color: var(--coral-text);
  font-weight: 600;
}
.pk-mark {
  width: 14px;
  color: var(--coral-text);
}
.pk-name {
  font-size: var(--text-dd-item);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pk-ver {
  font-size: var(--text-sm);
  color: var(--soft);
  white-space: nowrap;
}
.pk-row.on .pk-ver {
  color: var(--coral-text);
}
.pk-scn {
  display: inline-flex;
  gap: 3px;
}
.pk-note {
  margin: 4px 14px 10px;
}
</style>

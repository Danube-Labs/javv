<script setup lang="ts">
/**
 * The settings shell (SCREENS §13; prototype screens-config.jsx `Settings` → `.set-*` CSS):
 * left sub-nav + scope strip + routed panel. Sections are capability-hidden from the nav (A-4);
 * the router guard reroutes direct hits. Save bars belong to the editable panels, not the shell.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import SectionNav from '@/components/ui/SectionNav.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'

import { SCOPE_COPY, SETTINGS_SECTIONS } from './sections'

const auth = useAuthStore()
const clusterStore = useClusterStore()
const route = useRoute()

const sections = computed(() => SETTINGS_SECTIONS.filter((s) => auth.hasCapability(s.capability)))
const scopeOf = (key: string) => SETTINGS_SECTIONS.find((s) => s.key === key)!.scope
const navItems = computed(() =>
  sections.value.map((s) => ({ key: s.key, label: s.label, icon: s.icon, to: `/settings/${s.key}` })),
)
/** The scopes the visible sections use, in the order they first appear: the legend's rows. */
const legend = computed(() => [...new Set(sections.value.map((s) => s.scope))])
const active = computed(
  () => SETTINGS_SECTIONS.find((s) => route.path.startsWith(`/settings/${s.key}`)) ?? null,
)
const scopeNote = computed(() => {
  if (!active.value) return null
  const copy = SCOPE_COPY[active.value.scope]
  const name = clusterStore.selected?.cluster_name
  return active.value.scope === 'cluster' && name
    ? { ...copy, note: `Applies to ${name} only. Other clusters keep their own settings.` }
    : copy
})
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div class="head-card head-card-fluid">
        <h1>Settings</h1>
        <p class="head-note">
          each section notes whether it applies per cluster, per scanner, or organization-wide
        </p>
      </div>
    </div>

    <div class="set-layout">
      <SectionNav :items="navItems" :active="active?.key ?? null" label="Settings sections">
        <template #trail="{ item }">
          <i
            class="scope-dot"
            role="img"
            :data-scope="scopeOf(item.key)"
            :aria-label="SCOPE_COPY[scopeOf(item.key)].label"
            :title="SCOPE_COPY[scopeOf(item.key)].label"
          />
        </template>
        <template #footer>
          <ul class="scope-legend" aria-label="What the dots mean">
            <li v-for="scope in legend" :key="scope">
              <i :data-scope="scope" aria-hidden="true" />{{ SCOPE_COPY[scope].label }}
            </li>
          </ul>
        </template>
      </SectionNav>

      <div class="set-panel">
        <div v-if="active && scopeNote" class="scope-strip" :data-scope="active.scope">
          <span class="scope-badge">{{ scopeNote.label }}</span>
          <span class="scope-note">{{ scopeNote.note }}</span>
        </div>
        <RouterView />
      </div>
    </div>
  </div>
</template>

<style scoped>
/* prototype .set-layout / .scope-* ported onto tokens; the .set-nav menu is SectionNav */
.set-layout {
  display: grid;
  grid-template-columns: var(--section-nav-w) 1fr;
  gap: 18px;
  align-items: stretch;
}
.scope-dot {
  position: absolute;
  right: 9px;
  top: 50%;
  transform: translateY(-50%);
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
[data-scope='cluster'] {
  --sc: var(--scope-cluster);
}
[data-scope='scanner'] {
  --sc: var(--scope-scanner);
}
[data-scope='org'] {
  --sc: var(--scope-org);
}
.scope-dot {
  background: var(--sc);
}
.scope-legend {
  list-style: none;
  margin: 6px 4px 2px;
  padding: 8px 0 0;
  border-top: 1px solid var(--line2);
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: var(--text-control);
  color: var(--soft);
}
.scope-legend li {
  display: flex;
  align-items: center;
  gap: 7px;
}
.scope-legend i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--sc);
  flex: none;
}
/* a white card, as the other Settings cards (operator 2026-11-07 on built pictures, issue 1127,
   D6 C): on --panel it read as too muted. The scope color stays on the badge alone (issue 652) */
.scope-strip {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 9px 13px;
  border-radius: 10px;
  margin-bottom: 14px;
  border: 1px solid var(--line);
  background: var(--card);
  box-shadow: var(--shadow);
}
.scope-badge {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--kev-fg);
  background: var(--sc);
  padding: 3px 9px;
  border-radius: 6px;
  flex: none;
}
.scope-note {
  font-size: var(--text-sweep-strong);
  color: var(--soft);
}
.set-panel {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
@media (width <= 1100px) {
  .set-layout {
    grid-template-columns: 1fr;
  }
  /* the menu is a wrapping row here and each tab is only as wide as its label, so a dot pinned
     to the tab's right edge lands on the last letter: it joins the row's flow instead */
  .scope-dot {
    position: static;
    transform: none;
    flex: none;
  }
  /* under the wrapped tabs, as one row */
  .scope-legend {
    flex: 1 0 100%;
    flex-direction: row;
    gap: 16px;
  }
}
</style>

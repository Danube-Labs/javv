<script setup lang="ts">
/**
 * The slate sidebar (issue 384 split — extracted from AppShell, no behavior change): 226px,
 * collapsible to a 64px icon rail (Nuxt UI sidebar grammar, state persisted per browser) —
 * brand block, grouped nav with the javv stroke icons + coral active bar, sweep-health footer
 * + the running versions from `/api/v1/meta` (issue 261), which link to the About page's full
 * stack (issue 341). Nav items whose screen is capability-gated are HIDDEN without the
 * capability (A-4).
 */
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { client } from '@/api/client'
import { getMetaApiV1MetaGet } from '@/api/generated'
import iconSvg from '@/assets/brand/icon.svg'
import { visibleNav } from '@/components/chrome/navModel'
import AppIcon from '@/components/ui/AppIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { logger } from '@/lib/logger'
import { useHealthStore } from '@/stores/health'

const auth = useAuthStore()
const clusterStore = useClusterStore()
const health = useHealthStore()

/* Nav structure lives in navModel.ts (M9f) — shared with the command palette. */
const nav = computed(() => visibleNav(auth.hasCapability))

const SIDEBAR_KEY = 'javv.sidebar.collapsed'
const collapsed = ref(localStorage.getItem(SIDEBAR_KEY) === '1')
function toggleSidebar() {
  collapsed.value = !collapsed.value
  localStorage.setItem(SIDEBAR_KEY, collapsed.value ? '1' : '0')
}

type RunningVersions = {
  version: string
  mapping_version: number
  envelope_versions: number[]
}
const running = ref<RunningVersions | null>(null)
const versionFailed = ref(false)
/* one fact per line: at the footer's 10px mono the sidebar fits ~30 characters, so a joined line
   wraps mid-phrase */
const versionLines = computed((): string[] => {
  const r = running.value
  if (!r) return versionFailed.value ? ['no version'] : []
  return [
    `v${r.version}`,
    `database schema ${r.mapping_version}`,
    `scanner schema ${Math.max(...r.envelope_versions)}`,
  ]
})
onMounted(async () => {
  const { data, response } = await getMetaApiV1MetaGet({ client })
  if (response?.ok && data) {
    running.value = data as RunningVersions
  } else {
    versionFailed.value = true
    logger.warn('meta_read_failed', { status: response?.status })
  }
})
</script>

<template>
  <nav class="sidebar" :class="{ collapsed }" aria-label="Primary">
    <div class="side-top">
      <RouterLink to="/overview" class="side-brand" :title="collapsed ? 'javv: Overview' : undefined">
        <img :src="iconSvg" alt="" width="32" height="32" />
        <span v-if="!collapsed" class="side-word"><b>javv</b><span>by Danube Labs</span></span>
      </RouterLink>
      <button
        class="side-collapse"
        :aria-expanded="!collapsed"
        :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        @click="toggleSidebar"
      >
        <AppIcon name="sidebar" :size="16" />
      </button>
    </div>
    <div class="side-nav">
      <div v-for="g in nav" :key="g.group" class="side-group">
        <div v-if="!collapsed" class="side-group-label"><i class="side-group-dot" :style="{ background: g.accent }" aria-hidden="true" />{{ g.group }}</div>
        <div v-else class="side-sep" aria-hidden="true" />
        <RouterLink
          v-for="i in g.items"
          :key="i.to"
          :to="i.to"
          class="side-item"
          :title="collapsed ? i.label : undefined"
        >
          <AppIcon :name="i.icon" :size="17" />
          <span v-if="!collapsed">{{ i.label }}</span>
        </RouterLink>
      </div>
    </div>
    <div class="side-foot">
      <div
        class="sweep"
        :title="collapsed ? `${health.statusLabel} · ${clusterStore.clusters.length} cluster${clusterStore.clusters.length === 1 ? '' : 's'}` : undefined"
      >
        <span class="sweep-dot" :class="{ down: health.degraded }" aria-hidden="true" />
        <div v-if="!collapsed">
          <b>{{ health.statusLabel }}</b>
          <span>{{ clusterStore.clusters.length }} cluster{{ clusterStore.clusters.length === 1 ? '' : 's' }} · live</span>
        </div>
      </div>
      <RouterLink
        v-if="!collapsed && versionLines.length"
        to="/about"
        class="side-version"
        title="The JAVV release, the database schema and the newest scanner schema that JAVV accepts. About shows all the versions."
      >
        <span v-for="line in versionLines" :key="line">{{ line }}</span>
      </RouterLink>
    </div>
  </nav>
</template>

<style scoped>
/* ---- sidebar (prototype .sidebar family, via the side-chrome tokens) ---- */
.sidebar {
  width: var(--sidebar-w);
  flex: none;
  background: var(--slate);
  color: var(--side-fg);
  display: flex;
  flex-direction: column;
  padding: 16px 14px;
  overflow: hidden;
  transition: width var(--dur-panel) var(--ease-out);
}
.sidebar.collapsed {
  width: var(--sidebar-w-rail);
  padding: 16px 10px;
}
@media (prefers-reduced-motion: reduce) {
  .sidebar {
    transition: none;
  }
}
.side-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding-bottom: 18px;
}
.collapsed .side-top {
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.side-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 6px 8px 0 8px;
  text-decoration: none;
}
.collapsed .side-brand {
  padding: 0;
}
.side-collapse {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  margin-top: 6px;
  border: none;
  border-radius: 7px;
  background: var(--side-control-bg);
  color: var(--side-fg);
  transition:
    background var(--dur-quick),
    color var(--dur-quick);
}
.side-collapse:hover {
  background: var(--side-control-hover-bg);
  color: var(--side-fg-hover);
}
.side-collapse:active {
  background: var(--side-control-active-bg);
}
.side-collapse:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.side-word {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}
.side-word b {
  font-size: var(--text-brand-word);
  color: var(--side-brand-fg);
  letter-spacing: -0.03em;
}
.side-word span {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--side-credit);
  letter-spacing: 0.04em;
  margin-top: 2px;
}
.side-nav {
  flex: 1;
}
.side-group {
  margin-bottom: 14px;
}
.side-group-dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-right: 7px;
  vertical-align: 1px;
}
.side-group-label {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--side-label);
  padding: 0 10px 8px;
  white-space: nowrap;
}
.side-sep {
  height: 1px;
  background: var(--side-foot-line);
  margin: 0 8px 10px;
}
.side-item {
  display: flex;
  align-items: center;
  gap: 11px;
  width: 100%;
  padding: 9px 10px;
  border-radius: 9px;
  color: var(--side-fg);
  font-size: var(--text-nav-item);
  text-decoration: none;
  transition: color 0.12s;
  position: relative;
  white-space: nowrap;
}
.collapsed .side-item {
  justify-content: center;
  padding: 9px 0;
}
.side-item:hover {
  background: var(--side-hover-bg);
  color: var(--side-fg-hover);
}
.side-item.router-link-active {
  background: var(--side-on-bg);
  color: var(--side-on-fg);
}
.side-item.router-link-active::before {
  content: '';
  position: absolute;
  left: -14px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--coral);
}
.collapsed .side-item.router-link-active::before {
  left: -10px;
}
.side-item.router-link-active svg {
  color: var(--coral);
}
.side-foot {
  border-top: 1px solid var(--side-foot-line);
  padding-top: 14px;
  margin-top: 8px;
}
.sweep {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: var(--text-sm);
  color: var(--side-foot-fg);
}
.collapsed .sweep {
  justify-content: center;
  padding: 4px 0;
}
.sweep div {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}
.sweep b {
  color: var(--side-foot-strong);
  font-size: var(--text-sweep-strong);
  font-weight: 500;
}
.sweep span {
  color: var(--side-foot-dim);
  font-size: var(--text-facet-label);
  font-family: var(--font-mono);
}
.sweep-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--health-ok-dot);
  flex: none;
  box-shadow: 0 0 0 3px var(--sweep-ok-ring);
}
.sweep-dot.down {
  background: var(--health-down-fg);
  box-shadow: none;
}
.side-version {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--side-version);
  margin-top: 8px;
  padding: 4px 6px;
  border-radius: 7px;
  letter-spacing: 0.04em;
  text-decoration: none;
  transition:
    background var(--dur-quick),
    color var(--dur-quick);
}
/* the side-item grammar: the sidebar's own wash, pressed and focus ring */
.side-version:hover {
  background: var(--side-hover-bg);
  color: var(--side-fg-hover);
}
.side-version:active {
  background: var(--side-active-bg);
}
.side-version:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
@media (prefers-reduced-motion: reduce) {
  .side-version {
    transition: none;
  }
}
</style>

<script setup lang="ts">
/**
 * Global chrome (SCREENS / prototype fidelity): the slate sidebar (extracted to
 * components/chrome/SideNav.vue, issue 384) and the 56px topbar (cluster switcher · global
 * time picker · search/bell slots (M9f, disabled) · avatar), plus the health/freshness/history
 * banners and the routed content column. Owns the global range ⇄ URL sync and the
 * health-polling lifecycle.
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterView, useRoute, useRouter } from 'vue-router'

import ClusterSwitcher from '@/components/chrome/ClusterSwitcher.vue'
import CommandPalette from '@/components/chrome/CommandPalette.vue'
import NotificationBell from '@/components/chrome/NotificationBell.vue'
import SideNav from '@/components/chrome/SideNav.vue'
import UserMenu from '@/components/chrome/UserMenu.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import CrashBoundary from '@/components/system/CrashBoundary.vue'
import BackendHealthBanner from '@/components/system/BackendHealthBanner.vue'
import RetirementCountdownBanner from '@/components/system/RetirementCountdownBanner.vue'
import ScannerFreshnessBanner from '@/components/system/ScannerFreshnessBanner.vue'
import GlobalTimePicker from '@/components/time-travel/GlobalTimePicker.vue'
import ToastStack from '@/components/ui/ToastStack.vue'
import { useGlobalUrlStamp } from '@/composables/useGlobalUrlStamp'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useHealthStore } from '@/stores/health'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { isColdStart } from '@/system/coldStart'
import { lastDataAt } from '@/system/freshness'
import { clusterFromQuery, ttFromQuery } from '@/system/globalUrl'

const auth = useAuthStore()
const clusterStore = useClusterStore()
const health = useHealthStore()
const timeTravel = useTimeTravelStore()
const route = useRoute()
const router = useRouter()

/* ---- the global range ⇄ URL (restorable-state rule, audit 343) ---- */
// restore BEFORE child views mount, so their first reads already carry the range
const fromUrl = ttFromQuery(route.query)
if (fromUrl) {
  if (fromUrl.t !== null) {
    timeTravel.rewindTo(fromUrl.t)
    timeTravel.setWindow(fromUrl.win, `→ ${lastDataAt(fromUrl.t)}`)
  } else {
    // sub-hour windows label in minutes — rounding 30min to "0 hours" lied (operator catch)
    const hours = fromUrl.win * 24
    const label =
      fromUrl.win >= 1
        ? `Last ${fromUrl.win} day${fromUrl.win === 1 ? '' : 's'}`
        : hours >= 1
          ? `Last ${Math.round(hours)} hour${Math.round(hours) === 1 ? '' : 's'}`
          : `Last ${Math.max(1, Math.round(hours * 60))} minutes`
    timeTravel.setWindow(fromUrl.win, label)
  }
}
// deep link's tenant (issue 433) — resolved against the registry once fetchClusters lands
const urlCluster = clusterFromQuery(route.query)

useGlobalUrlStamp()

/** Zero-clusters cold start (M9f) — which sections stay live lives in `isColdStart`. */
const coldStart = computed(() =>
  isColdStart({ none: clusterStore.none, section: route.meta.section as string | undefined }),
)

/** Section identity echo (§8.5 specimen): the route's sidebar-group accent, exposed as a CSS
 * var the head-card's top bar reads — wayfinding chroma only. */
const sectAccent = computed(() => {
  const sect = route.meta.section as string | undefined
  return sect ? { '--sect-accent': `var(--sect-${sect})` } : {}
})

/* ---- ⌘K command palette (M9f slice 2) ---- */
const paletteOpen = ref(false)
const metaKeyLabel = /mac/i.test(navigator.platform) ? '⌘' : 'ctrl+'
function onGlobalKey(e: KeyboardEvent) {
  if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    paletteOpen.value = !paletteOpen.value
  }
}

onMounted(() => {
  health.startPolling()
  void clusterStore.fetchClusters(urlCluster)
  document.addEventListener('keydown', onGlobalKey)
})
onUnmounted(() => {
  health.stopPolling()
  document.removeEventListener('keydown', onGlobalKey)
})
</script>

<template>
  <div class="shell">
    <SideNav />

    <div class="main">
      <header class="topbar">
        <ClusterSwitcher />
        <div class="topbar-mid">
          <GlobalTimePicker />
        </div>
        <div class="topbar-right">
          <button type="button" class="global-search" aria-label="Global search" @click="paletteOpen = true">
            <AppIcon name="search" :size="14" />
            <span class="gs-hint">Search CVE, image, namespace…</span>
            <kbd>{{ metaKeyLabel }}K</kbd>
          </button>
          <NotificationBell />
          <UserMenu />
        </div>
      </header>

      <BackendHealthBanner />
      <ScannerFreshnessBanner />
      <RetirementCountdownBanner />
      <p v-if="clusterStore.failed && clusterStore.clusters.length === 0" class="load-error" role="alert">
        Cluster list unavailable, and every read needs it. Check the backend, then reload.
      </p>
      <Transition name="t-fade">
        <div v-if="!timeTravel.isNow" class="sys-line tone-hist" role="status">
          <AppIcon class="sys-icon" name="rewind" :size="15" />
          Viewing history: as scanned at
          <span class="mono">{{ new Date(timeTravel.t as string).toLocaleString(undefined, { hour12: false }) }}</span>
          <button class="back-to-now" @click="timeTravel.backToNow()">Back to now</button>
        </div>
      </Transition>

      <main class="content" :class="{ 'content-wide': $route.meta.wide }" :style="sectAccent">
        <EmptyState
          v-if="coldStart"
          icon="layers"
          title="No clusters registered yet"
          hint="JAVV fills in once the first scanner envelope lands. Create a scanner token, deploy the scanner CronJobs to a cluster, and the first committed cycle appears here."
        >
          <UiButton
            v-if="auth.hasCapability('can_manage_tokens')"
            variant="primary"
            @click="router.push('/settings/tokens')"
          >
            Create a scanner token
          </UiButton>
        </EmptyState>
        <CrashBoundary v-else>
          <RouterView />
        </CrashBoundary>
      </main>
    </div>

    <ToastStack />
    <CommandPalette v-if="paletteOpen" @close="paletteOpen = false" />
  </div>
</template>

<style scoped>
.shell {
  /* desktop-first ops dashboard: 1024px design floor (audit ruling) — below it the app
     scrolls as ONE intact piece; a true responsive pass is an M9f decision, not an accident */
  min-width: 1024px;
  display: flex;
  min-height: 100vh;
}

/* ---- topbar (prototype .topbar family) ---- */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  height: 56px;
  flex: none;
  background: var(--card);
  border-bottom: 1px solid var(--line);
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 0 22px;
}
.topbar-mid {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
}
.topbar-right {
  display: flex;
  flex: 0 1 auto;
  min-width: 0;
  align-items: center;
  gap: 14px;
}
/* topbar control register (operator, 2026-07-17): one 40px height across cluster switcher /
   time picker / search; --panel on the white topbar read as "old" and its row-hover wash was
   invisible — the search sits on the warm canvas (--bg) with the REAL control wash on hover */
.global-search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  /* 2px border — the operator's ruling with keep-beige: the 1px hairline read as washy */
  border: 2px solid var(--line);
  background: var(--bg);
  border-radius: 10px;
  padding: 0 12px;
  color: var(--soft);
  /* wide enough for the whole hint; gives way at the 1024 floor so the time picker keeps one
     line (issue 647), and there the hint truncates */
  flex: 0 1 290px;
  min-width: 150px;
  font-family: var(--font-ui);
  cursor: default;
}
.global-search:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.global-search:active {
  background: var(--line2);
}
.gs-hint {
  flex: 1;
  text-align: left;
  color: var(--ink);
  font-size: var(--text-control);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.global-search kbd {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  background: var(--card);
  border: 1px solid var(--line2);
  border-radius: var(--r-chip);
  padding: 1px 5px;
}.icon-btn {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--card);
  color: var(--soft);
  cursor: default;
}
.icon-btn:disabled {
  cursor: default;
  opacity: 0.6;
}

/* ---- banners + content ---- */
.back-to-now {
  margin-left: auto;
  border: 1px solid var(--hist-line);
  border-radius: var(--r-chip);
  background: var(--card);
  color: var(--hist-fg);
  font-size: var(--text-sm);
  padding: 3px 10px;
  cursor: default;
}
.content {
  flex: 1;
  max-width: var(--screen-max-w);
  width: 100%;
  margin: 0 auto;
  padding: var(--content-pad);
  padding-bottom: 72px;
}
/* data-dense screens (route meta `wide`) use the full viewport instead of the 1380px cap —
   an internal table scrollbar beside dead margin is worse than a wide table (operator ruling). */
.content-wide {
  max-width: none;
}
</style>

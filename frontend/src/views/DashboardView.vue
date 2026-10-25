<script setup lang="ts">
/**
 * One dashboard (issue 440, S7; SCREENS §20). The server answers 404 for a dashboard that does
 * not exist and for one this user cannot see, so both get the "not found" page (decision Q3).
 * Every panel reads the selected cluster and time range (D8). The scanner switch starts on the
 * scanner the owner saved and keeps the viewer's choice in the URL, so a link opens the same
 * view; a panel pinned to one scanner does not follow it (Q7).
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getDashboardApiV1DashboardsDashboardIdGet, type DashboardPanel } from '@/api/generated'
import DashboardGrid from '@/components/dashboards/DashboardGrid.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useCsvExport } from '@/composables/useCsvExport'
import { useStretchWidth } from '@/composables/useStretchWidth'
import { EXPORT_PATH } from '@/dashboards/files'
import { changedLine, parseScanner, sharingLine } from '@/dashboards/layout'
import { readFailureCopy } from '@/findings/failureCopy'
import { SCANNER_SWITCH_OPTS, type ScannerLens } from '@/lib/scannerLens'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'
import { lastDataAt } from '@/system/freshness'
import NotFoundView from '@/views/NotFoundView.vue'

interface DashboardDoc {
  dashboard_id: string
  name: string
  description: string
  owner: string
  scanner: ScannerLens
  panels: DashboardPanel[]
  sharing: string
  roles: string[]
  updated_at: string
  updated_by: string
}

const route = useRoute()
const router = useRouter()
const clusterStore = useClusterStore()
const timeTravel = useTimeTravelStore()
const toast = useToastStore()

const dash = ref<DashboardDoc | null>(null)
/** the header card stays on the page while the dashboard loads, so it stretches when the
 * name and the line under it arrive (issue 902) */
const headCard = ref<HTMLElement | null>(null)
useStretchWidth(headCard)
const notFound = ref(false)
const failedStatus = ref<number | null>(null)

async function load(id: string) {
  dash.value = null
  notFound.value = false
  failedStatus.value = null
  try {
    const { response, data } = await getDashboardApiV1DashboardsDashboardIdGet({ path: { dashboard_id: id } })
    // the page is reused across dashboards: a late answer for one the user left is dropped
    if (route.params.id !== id) return
    if (response?.status === 404) notFound.value = true
    else if (response?.ok && data) dash.value = data as unknown as DashboardDoc
    else failedStatus.value = response?.status ?? 0
  } catch {
    if (route.params.id === id) failedStatus.value = 0
  }
}
watch(
  () => route.params.id,
  (id) => {
    if (typeof id === 'string') void load(id)
  },
  { immediate: true },
)

const scanner = computed<ScannerLens>({
  get: () => parseScanner(route.query.scanner) ?? dash.value?.scanner ?? 'all',
  set: (value) => void router.replace({ query: { ...route.query, scanner: value } }),
})

const exporter = useCsvExport({
  path: EXPORT_PATH,
  filename: () => `dashboard-${dash.value?.dashboard_id ?? 'export'}.ndjson`,
  event: 'dashboard_export_failed',
  onCapped: () => toast.error('The export failed. Try again.'),
  onFailed: (status) => toast.error(readFailureCopy(status, 'The export failed. Check the backend, then try again.')),
  onDone: (name) => toast.success(`Saved ${name}`),
})
</script>

<template>
  <NotFoundView v-if="notFound" />

  <div v-else class="screen">
    <div class="screen-head">
      <div ref="headCard" class="head-card head-card-fluid">
        <h1>{{ dash?.name ?? 'Dashboard' }}</h1>
        <template v-if="dash">
          <p v-if="dash.description" class="head-note dash-desc">{{ dash.description }}</p>
          <p class="head-note dash-meta">
            <span class="dash-share"
              ><AppIcon :name="dash.sharing === 'private' ? 'key' : 'users'" :size="12" />{{
                sharingLine(dash.sharing, dash.roles)
              }}</span
            >
            · owner <span class="mono-cell">{{ dash.owner }}</span> ·
            <span :title="lastDataAt(dash.updated_at)">{{ changedLine(dash.updated_at, dash.updated_by) }}</span>
            <template v-if="clusterStore.selected?.cluster_name">
              · <b class="mono-cell">{{ clusterStore.selected.cluster_name }}</b>
            </template>
          </p>
        </template>
      </div>
      <div v-if="dash" class="head-actions">
        <UiSegControl v-model="scanner" :options="SCANNER_SWITCH_OPTS" />
        <UiButton
          variant="control"
          :disabled="exporter.exporting.value"
          @click="exporter.run({ dashboard_id: dash.dashboard_id })"
        >
          <AppIcon name="download" :size="13" />{{ exporter.exporting.value ? 'Exporting…' : 'Export' }}
        </UiButton>
      </div>
    </div>

    <UiSkeleton v-if="!dash && failedStatus === null" :height="220" label="Loading the dashboard" />

    <p v-else-if="!dash" class="load-error" role="alert">
      {{ readFailureCopy(failedStatus, 'The dashboard is unavailable. Check the backend, then reload.') }}
    </p>

    <template v-else>
      <EmptyState
        v-if="!clusterStore.selectedId"
        icon="layers"
        title="No cluster to show"
        hint="Each panel shows the data of the cluster that you select at the top of the page."
      />
      <EmptyState
        v-else-if="dash.panels.length === 0"
        icon="columns"
        title="This dashboard has no panels"
        hint="Its owner has not added a panel yet."
      />
      <DashboardGrid
        v-else
        :panels="dash.panels"
        :cluster-id="clusterStore.selectedId"
        :t="timeTravel.t"
        :window-days="timeTravel.windowDays"
        :scanner="scanner"
      />
    </template>
  </div>
</template>

<style scoped>
.head-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 10px;
}
.dash-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.dash-share {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>

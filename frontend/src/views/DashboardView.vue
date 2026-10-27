<script setup lang="ts">
/**
 * One dashboard (issue 440, S7; SCREENS §20). The server answers 404 for a dashboard that does
 * not exist and for one this user cannot see, so both get the "not found" page (decision Q3).
 * Every panel reads the selected cluster and time range (D8). The scanner switch starts on the
 * scanner the owner saved and keeps the viewer's choice in the URL, so a link opens the same
 * view; a panel pinned to one scanner does not follow it (Q7).
 *
 * Edit mode (`?edit=1`, S8) is for the owner or an admin (D3). The page keeps a draft of the
 * panels; gridstack moves them, and the save bar saves the draft. A save sends the panels only
 * when the layout changed, so a stored layout is not checked again for nothing (PR B), and it
 * sends the revision it read: a dashboard that somebody changed since is refused (409, D4).
 * The name, description, sharing and opening scanner join the same draft and the same save; the
 * save sends only the fields that changed (S8c).
 */
import { computed, defineAsyncComponent, defineComponent, h, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { STORE_READ_ONLY_TYPE } from '@/api/problem'
import {
  getDashboardApiV1DashboardsDashboardIdGet,
  updateDashboardApiV1DashboardsDashboardIdPatch,
  type DashboardPanel,
  type UpdateDashboard,
} from '@/api/generated'
import AddPanelDialog from '@/components/dashboards/AddPanelDialog.vue'
import DashboardDetailsDialog from '@/components/dashboards/DashboardDetailsDialog.vue'
import DashboardGrid from '@/components/dashboards/DashboardGrid.vue'
import PanelSettings from '@/components/dashboards/PanelSettings.vue'
import RemoveDashboardDialog from '@/components/dashboards/RemoveDashboardDialog.vue'
import SaveBar from '@/components/settings/SaveBar.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiRoleNote from '@/components/ui/UiRoleNote.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useCsvExport } from '@/composables/useCsvExport'
import { useStretchWidth } from '@/composables/useStretchWidth'
import { detailsChange, detailsOf, sameDetails, type DashboardDetails, type Sharing } from '@/dashboards/details'
import {
  addedPanel,
  editRefusal,
  MAX_PANELS,
  PANEL_CAP_NOTE,
  fromDraft,
  sameLayout,
  saveFailureCopy,
  toDraft,
  withPlaces,
  withSettings,
  type DraftPanel,
  type PanelPlace,
  type PanelSettings as Settings,
} from '@/dashboards/edit'
import { EXPORT_PATH } from '@/dashboards/files'
import { changedLine, parseScanner, sharingLine } from '@/dashboards/layout'
import { readFailureCopy } from '@/findings/failureCopy'
import { logger } from '@/lib/logger'
import { SCANNER_SWITCH_OPTS, type ScannerLens } from '@/lib/scannerLens'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { useToastStore } from '@/stores/toast'
import { lastDataAt } from '@/system/freshness'
import NotFoundView from '@/views/NotFoundView.vue'

/** gridstack is in the edit grid's own chunk, which only edit mode loads (decision Q5) */
const DashboardEditGrid = defineAsyncComponent({
  loader: () => import('@/components/dashboards/DashboardEditGrid.vue'),
  loadingComponent: defineComponent(() => () => h(UiSkeleton, { height: 220, label: 'Loading edit mode' })),
  errorComponent: defineComponent(
    () => () => h('p', { class: 'load-error', role: 'alert' }, 'Edit mode did not load. Reload the page.'),
  ),
  delay: 200,
})

interface DashboardDoc {
  dashboard_id: string
  name: string
  description: string
  owner: string
  scanner: ScannerLens
  panels: DashboardPanel[]
  sharing: Sharing
  roles: string[]
  updated_at: string
  updated_by: string
  revision: number
}

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
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

/** why this user cannot change the dashboard, or null */
const refusal = computed(() => (dash.value ? editRefusal(auth.user?.username, auth.hasCapability, dash.value.owner) : null))
const editing = computed(() => route.query.edit === '1' && dash.value !== null && refusal.value === null)

function setEditing(on: boolean) {
  const query = { ...route.query }
  if (on) query.edit = '1'
  else delete query.edit
  void router.replace({ query })
}

const draft = ref<DraftPanel[]>([])
/** the saved panels as edit mode shows them: a save sends panels only when they differ. Its
 * keys are the draft's, so the first places gridstack gives move only the saved panels. */
const baseline = ref<DraftPanel[]>([])
/** a new key makes a new edit grid, so a discard starts gridstack again from the saved panels */
const gridKey = ref(0)
const busy = ref(false)
/** a refused save stays next to the save bar until the next save or discard */
const saveError = ref<string | null>(null)
const settingsKey = ref<string | null>(null)
/** the Settings button that opened the panel settings, and the panel it belongs to */
const settingsTrigger = ref<HTMLElement | null>(null)
const settingsAnchor = computed(() => settingsTrigger.value?.closest<HTMLElement>('.grid-stack-item-content') ?? null)
const adding = ref(false)
/** the name, sharing and opening scanner in the draft, and as saved */
const details = ref<DashboardDetails | null>(null)
const detailsBase = ref<DashboardDetails | null>(null)
const detailsOpen = ref(false)
const removing = ref(false)
const full = computed(() => draft.value.length >= MAX_PANELS)

function startDraft() {
  if (!dash.value) return
  draft.value = toDraft(dash.value.panels)
  baseline.value = draft.value
  details.value = detailsOf(dash.value)
  detailsBase.value = details.value
  settingsKey.value = null
  adding.value = false
  detailsOpen.value = false
  saveError.value = null
  gridKey.value++
}
watch(editing, (on) => {
  if (on) startDraft()
})

const detailsChanged = computed(
  () => details.value !== null && detailsBase.value !== null && !sameDetails(detailsBase.value, details.value),
)
const dirty = computed(
  () => editing.value && (detailsChanged.value || !sameLayout(fromDraft(draft.value), fromDraft(baseline.value))),
)
const settingsPanel = computed(() => draft.value.find((p) => p.key === settingsKey.value) ?? null)

function onReady(places: PanelPlace[]) {
  draft.value = withPlaces(draft.value, places)
  baseline.value = withPlaces(baseline.value, places)
}
function onMoved(places: PanelPlace[]) {
  draft.value = withPlaces(draft.value, places)
}
function openSettings(key: string, trigger: HTMLElement) {
  settingsKey.value = key
  settingsTrigger.value = trigger
}
function applySettings(settings: Settings) {
  draft.value = draft.value.map((p) => (p.key === settingsKey.value ? withSettings(p, settings) : p))
  settingsKey.value = null
}
function addPanel(choice: Parameters<typeof addedPanel>[1]) {
  draft.value = [...draft.value, addedPanel(draft.value, choice)]
  adding.value = false
}
function removePanel(key: string) {
  draft.value = draft.value.filter((p) => p.key !== key)
}
function applyDetails(next: DashboardDetails) {
  details.value = next
  detailsOpen.value = false
}
function onRemoved() {
  toast.success(`Dashboard “${dash.value?.name ?? ''}” removed`)
  void router.push('/dashboards')
}

async function save() {
  if (!dash.value) return
  const id = dash.value.dashboard_id
  // the user can go on editing while the save runs: what was sent becomes the saved state, and a
  // change made since stays unsaved
  const sentDraft = draft.value
  const sentDetails = details.value
  const panels = fromDraft(sentDraft)
  const body: UpdateDashboard = { revision: dash.value.revision }
  if (sentDetails && detailsBase.value) Object.assign(body, detailsChange(detailsBase.value, sentDetails))
  if (!sameLayout(panels, fromDraft(baseline.value))) body.panels = panels
  busy.value = true
  saveError.value = null
  const { response, data, error } = await updateDashboardApiV1DashboardsDashboardIdPatch({
    path: { dashboard_id: id },
    body,
  })
  busy.value = false
  if (!response?.ok || !data) logger.warn('dashboard_save_failed', { status: response?.status ?? 0 })
  else toast.success('Dashboard saved.')
  // the page is reused across dashboards: the answer for one that the user left changes nothing here
  if (route.params.id !== id) return
  if (!response?.ok || !data) {
    const readOnly = (error as { type?: unknown } | undefined)?.type === STORE_READ_ONLY_TYPE
    saveError.value = saveFailureCopy(response?.status ?? 0, readOnly)
    return
  }
  dash.value = data as unknown as DashboardDoc
  baseline.value = sentDraft
  detailsBase.value = detailsOf(dash.value)
  if (details.value === sentDetails) details.value = detailsBase.value
}
</script>

<template>
  <NotFoundView v-if="notFound" />

  <div v-else class="screen">
    <div class="screen-head">
      <div ref="headCard" class="head-card head-card-fluid">
        <h1>{{ editing ? `Editing ${details?.name ?? dash?.name}` : (dash?.name ?? 'Dashboard') }}</h1>
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
        <UiSegControl v-model="scanner" :options="SCANNER_SWITCH_OPTS" label="Scanner" />
        <!-- the save bar holds the only ways out of unsaved changes: Discard and Save changes -->
        <template v-if="editing">
          <UiButton
            variant="control"
            :disabled="full"
            :aria-describedby="full ? 'panel-cap-note' : undefined"
            @click="adding = true"
          >
            <AppIcon name="plus" :size="13" />Add panel
          </UiButton>
          <UiRoleNote v-if="full" id="panel-cap-note" icon="info">{{ PANEL_CAP_NOTE }}</UiRoleNote>
          <UiButton variant="control" @click="detailsOpen = true">
            <AppIcon name="users" :size="13" />Name and sharing
          </UiButton>
          <UiButton variant="control" @click="removing = true"><AppIcon name="trash" :size="13" />Remove</UiButton>
          <UiButton variant="ghost" :disabled="dirty" @click="setEditing(false)">Exit edit</UiButton>
        </template>
        <template v-else>
          <UiButton
            variant="control"
            :disabled="exporter.exporting.value"
            @click="exporter.run({ dashboard_id: dash.dashboard_id })"
          >
            <AppIcon name="download" :size="13" />{{ exporter.exporting.value ? 'Exporting…' : 'Export' }}
          </UiButton>
          <UiButton
            variant="control"
            :disabled="refusal !== null"
            :aria-describedby="refusal ? 'no-edit-note' : undefined"
            @click="setEditing(true)"
          >
            <AppIcon name="gear" :size="13" />Edit dashboard
          </UiButton>
          <UiRoleNote v-if="refusal" id="no-edit-note">{{ refusal }}</UiRoleNote>
        </template>
      </div>
    </div>

    <div v-if="editing" class="dash-save">
      <SaveBar :dirty="dirty" :busy="busy" @discard="startDraft" @save="save" />
      <p v-if="saveError" class="load-error dash-save-error" role="alert">{{ saveError }}</p>
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
        v-else-if="editing && draft.length === 0"
        icon="columns"
        title="This dashboard has no panels"
        hint="Add panels from the catalog. You can move each panel, and set its scanner, width and height."
      >
        <UiButton variant="primary" @click="adding = true"><AppIcon name="plus" :size="13" />Add panel</UiButton>
      </EmptyState>
      <DashboardEditGrid
        v-else-if="editing"
        :key="gridKey"
        :panels="draft"
        :cluster-id="clusterStore.selectedId"
        :t="timeTravel.t"
        :window-days="timeTravel.windowDays"
        :scanner="scanner"
        @ready="onReady"
        @moved="onMoved"
        :active="settingsKey"
        @settings="openSettings"
        @remove="removePanel"
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

    <AddPanelDialog
      v-if="adding && editing"
      :count="draft.length"
      :cluster-id="clusterStore.selectedId"
      :t="timeTravel.t"
      :window-days="timeTravel.windowDays"
      :dashboard-scanner="scanner"
      @close="adding = false"
      @add="addPanel"
    />
    <DashboardDetailsDialog
      v-if="detailsOpen && editing && details"
      :details="details"
      mode="edit"
      @close="detailsOpen = false"
      @apply="applyDetails"
    />
    <RemoveDashboardDialog
      v-if="removing && editing && dash"
      :dashboard-id="dash.dashboard_id"
      :name="dash.name"
      :revision="dash.revision"
      @close="removing = false"
      @removed="onRemoved"
    />
    <PanelSettings
      v-if="settingsPanel && settingsAnchor"
      :key="settingsPanel.key"
      :panel="settingsPanel"
      :anchor="settingsAnchor"
      :trigger="settingsTrigger"
      :dashboard-scanner="scanner"
      @close="settingsKey = null"
      @apply="applySettings"
    />
  </div>
</template>

<style scoped>
.screen-head {
  gap: 16px;
}
/* edit mode has five controls: next to a long name they go to a second row, not past the edge */
.head-actions {
  display: flex;
  flex: 0 1 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
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
/* the save bar stays in view while the user moves panels further down the page */
.dash-save {
  position: sticky;
  top: 8px;
  z-index: 5;
  margin: 0 0 18px;
}
.dash-save :deep(.save-bar) {
  margin-top: 0;
}
.dash-save-error {
  margin: 8px 0 0;
}
</style>

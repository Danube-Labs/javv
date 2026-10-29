<script setup lang="ts">
/**
 * Dashboards (issue 440, S7; SCREENS §20): the dashboards that the user can see, in the Saved
 * views card grid. The server applies the sharing rule, so the list holds only what this user
 * may open (decision Q3). Export downloads them all as one file and needs no `can_export` (D7);
 * import needs `can_edit_dashboards` and makes the importer the owner (D6). New dashboard needs
 * it too: it asks for the details, makes the dashboard, and opens it in edit mode (S8c).
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { STORE_READ_ONLY_TYPE } from '@/api/problem'
import { createDashboardApiV1DashboardsPost, listDashboardsApiV1DashboardsGet } from '@/api/generated'
import DashboardDetailsDialog from '@/components/dashboards/DashboardDetailsDialog.vue'
import ImportDashboardsDialog from '@/components/dashboards/ImportDashboardsDialog.vue'
import GridPager from '@/components/findings/GridPager.vue'
import SavedCard from '@/components/saved/SavedCard.vue'
import SavedGrid from '@/components/saved/SavedGrid.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiRoleNote from '@/components/ui/UiRoleNote.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { usePagedSlice } from '@/composables/usePagedSlice'
import { useCsvExport } from '@/composables/useCsvExport'
import type { DashboardPanel } from '@/api/generated'
import { NEW_DETAILS, createFailureCopy, newDashboardBody, type DashboardDetails } from '@/dashboards/details'
import { EXPORT_PATH, NO_IMPORT_NOTE } from '@/dashboards/files'
import { changedLine, sharingLine } from '@/dashboards/layout'
import { lastDataAt } from '@/system/freshness'
import { readFailureCopy } from '@/findings/failureCopy'
import { logger } from '@/lib/logger'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

interface DashboardDoc {
  dashboard_id: string
  name: string
  description: string
  owner: string
  panels: DashboardPanel[]
  sharing: string
  roles: string[]
  updated_at: string
  updated_by: string
}

const auth = useAuthStore()
const toast = useToastStore()
const router = useRouter()

const dashboards = ref<DashboardDoc[]>([])
const loaded = ref(false)
const failed = ref(false)
const failedStatus = ref<number | null>(null)
const importing = ref(false)
const creating = ref(false)
const createBusy = ref(false)
const createError = ref<string | null>(null)
const pager = usePagedSlice(() => dashboards.value, 10)

const canEdit = computed(() => auth.hasCapability('can_edit_dashboards'))

async function load() {
  const { response, data } = await listDashboardsApiV1DashboardsGet()
  failed.value = !response?.ok || !data
  failedStatus.value = response?.status ?? null
  dashboards.value = failed.value ? [] : ((data as { dashboards: DashboardDoc[] }).dashboards ?? [])
  loaded.value = true
}
onMounted(() => void load())

/** null = every dashboard the user can see; else the one dashboard the card exports */
const exportOne = ref<DashboardDoc | null>(null)
const exporter = useCsvExport({
  path: EXPORT_PATH,
  filename: (stamp) => (exportOne.value ? `dashboard-${exportOne.value.dashboard_id}.ndjson` : `dashboards-${stamp}.ndjson`),
  event: 'dashboards_export_failed',
  onCapped: () => toast.error('The export failed. Try again.'),
  onFailed: (status) => toast.error(readFailureCopy(status, 'The export failed. Check the backend, then try again.')),
  onDone: (name) => toast.success(`Saved ${name}`),
})

function onImported(created: number) {
  if (created > 0) toast.success(`${created} dashboard${created === 1 ? '' : 's'} imported`)
  void load()
}

function startCreate() {
  createError.value = null
  creating.value = true
}
async function create(details: DashboardDetails) {
  createBusy.value = true
  createError.value = null
  const { response, data, error } = await createDashboardApiV1DashboardsPost({ body: newDashboardBody(details) })
  createBusy.value = false
  const id = (data as { dashboard_id?: string } | undefined)?.dashboard_id
  if (!response?.ok || !id) {
    logger.warn('dashboard_create_failed', { status: response?.status ?? 0 })
    const readOnly = (error as { type?: unknown } | undefined)?.type === STORE_READ_ONLY_TYPE
    createError.value = createFailureCopy(response?.status ?? 0, readOnly)
    return
  }
  creating.value = false
  void router.push({ path: `/dashboards/${id}`, query: { edit: '1' } })
}

function exportAll() {
  exportOne.value = null
  void exporter.run({})
}
function exportDashboard(d: DashboardDoc) {
  exportOne.value = d
  void exporter.run({ dashboard_id: d.dashboard_id })
}
</script>

<template>
  <div class="screen">
    <div class="screen-head screen-head-band">
      <div class="head-card">
        <h1>Dashboards</h1>
        <p class="head-stat">
          <!-- a count not yet read, or refused, is unknown, not zero (issue 833, F5) -->
          <template v-if="loaded && !failed">{{ dashboards.length }}</template
          ><span v-else class="muted-dash">-</span><span class="head-unit"> dashboards</span>
        </p>
        <p class="head-note">the dashboards that you can see · each panel reads the selected cluster</p>
      </div>
      <div class="head-actions">
        <UiButton
          variant="primary"
          :disabled="!canEdit"
          :aria-describedby="canEdit ? undefined : 'no-import-note'"
          @click="startCreate"
        >
          <AppIcon name="plus" :size="13" />New dashboard
        </UiButton>
        <UiButton variant="control" bordered :disabled="exporter.exporting.value" @click="exportAll">
          <AppIcon name="download" :size="13" />{{ exporter.exporting.value ? 'Exporting…' : 'Export all' }}
        </UiButton>
        <UiButton
          variant="control"
          bordered
          :disabled="!canEdit"
          :aria-describedby="canEdit ? undefined : 'no-import-note'"
          @click="importing = true"
        >
          <AppIcon name="upload" :size="13" />Import
        </UiButton>
        <UiRoleNote v-if="!canEdit" id="no-import-note">{{ NO_IMPORT_NOTE }}</UiRoleNote>
      </div>
    </div>

    <UiSkeleton v-if="!loaded" :height="160" label="Loading dashboards" class="skel-gap" />

    <p v-else-if="failed" class="load-error" role="alert">
      {{ readFailureCopy(failedStatus, 'Dashboards unavailable. Check the backend, then reload.') }}
    </p>

    <EmptyState
      v-else-if="dashboards.length === 0"
      icon="columns"
      title="No dashboards yet"
      hint="A dashboard puts panels of Overview, Contributors and Scanner status on one page. Make a new one, or import a dashboard file."
    >
      <UiButton v-if="canEdit" variant="primary" @click="startCreate"><AppIcon name="plus" :size="13" />New dashboard</UiButton>
      <UiButton v-if="canEdit" variant="control" @click="importing = true">Import</UiButton>
    </EmptyState>

    <SavedGrid v-else>
      <SavedCard
        v-for="d in pager.shown.value"
        :key="d.dashboard_id"
        :title="d.name"
        :to="`/dashboards/${d.dashboard_id}`"
        :description="d.description"
        :owner="d.owner"
        :badge-tone="d.sharing === 'everyone' || d.sharing === 'roles' ? d.sharing : 'private'"
        @open="router.push(`/dashboards/${d.dashboard_id}`)"
      >
        <template #badge>
          <AppIcon :name="d.sharing === 'private' ? 'key' : 'users'" :size="12" /><span
            class="vc-badge-text"
            :title="sharingLine(d.sharing, d.roles)"
            >{{ sharingLine(d.sharing, d.roles) }}</span
          >
        </template>
        <template #summary>
          <span class="dash-sum">
            <span class="mono">{{ d.panels.length }} panel{{ d.panels.length === 1 ? '' : 's' }}</span>
            <span :title="lastDataAt(d.updated_at)"> · {{ changedLine(d.updated_at, d.updated_by) }}</span>
          </span>
        </template>
        <template #actions>
          <UiButton variant="mini" bordered :disabled="exporter.exporting.value" @click="exportDashboard(d)">
            <AppIcon name="download" :size="12" />Export
          </UiButton>
        </template>
      </SavedCard>
      <template #pager>
        <GridPager
          :total="dashboards.length"
          :page="pager.page.value"
          :size="pager.size.value"
          :shown="pager.shown.value.length"
          :has-prev="pager.page.value > 0"
          :has-next="pager.hasNext.value"
          @prev="pager.page.value -= 1"
          @next="pager.page.value += 1"
          @update:size="pager.setSize"
        />
      </template>
    </SavedGrid>

    <ImportDashboardsDialog v-if="importing" @close="importing = false" @imported="onImported" />
    <DashboardDetailsDialog
      v-if="creating"
      :details="NEW_DETAILS"
      mode="create"
      :busy="createBusy"
      :error="createError"
      @close="creating = false"
      @apply="create"
    />
  </div>
</template>

<style scoped>
.head-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: 10px;
}
/* the head buttons sit on the page paper (issue 1004, operator 2026-10-29): one size, a small
   lift. The primary takes the padding of the control variant (UiButton) */
.head-actions :deep(.ui-btn) {
  box-shadow: var(--control-lift);
}
.head-actions :deep(.ui-btn--primary) {
  padding: 6px 11px;
}
/* the Saved views summary is an italic line; here it is a count and a time */
.dash-sum {
  font-style: normal;
}
</style>

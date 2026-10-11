<script setup lang="ts">
/**
 * Data & OpenSearch panel (§13.7, FR-19/D26): the four setting groups (retention / rollover /
 * findings-cleanup / report-TTL) on one SaveBar — save PUTs only the changed groups
 * (`changedGroups`); the sweeps read the docs live, so edits apply at the next run. The
 * retention card lists EVERY index family (row 23): the append families share the ONE editable
 * window, protected families are read-only rows saying why. Snapshots and the OpenSearch
 * runtime display are focused sibling panels (SnapshotsCard / OpensearchRuntimeCard) — this
 * view owns only the settings form.
 */
import { computed, ref, watch } from 'vue'

import {
  getDataSettingsApiV1SettingsDataGet,
  putFindingsCleanupApiV1SettingsFindingsCleanupPut,
  putReportTtlApiV1SettingsReportTtlPut,
  putRetentionApiV1SettingsRetentionPut,
  putRolloverApiV1SettingsRolloverPut,
} from '@/api/generated'
import { client } from '@/api/client'
import DotWord from '@/components/chips/DotWord.vue'
import OpensearchRuntimeCard from '@/components/settings/OpensearchRuntimeCard.vue'
import SaveBar from '@/components/settings/SaveBar.vue'
import NoClusterState from '@/components/settings/NoClusterState.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import SnapshotsCard from '@/components/settings/SnapshotsCard.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useToastStore } from '@/stores/toast'

import {
  changedGroups,
  draftDirty,
  draftFromSettings,
  draftInvalid,
  FAMILY_ROWS,
  parseDraft,
  type DataDraft,
  type DataSettings,
} from './dataForm'

const clusterStore = useClusterStore()
const toast = useToastStore()

// ── settings (one SaveBar over the four groups) ────────────────────────────────────────────
const saved = ref<DataSettings | null>(null)
const draft = ref<DataDraft>({
  retention: '',
  maxAge: '',
  maxDocs: '',
  maxSize: '',
  cleanup: '',
  ttl: '',
})
const override = ref(false)
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

async function loadSettings(clusterId: string) {
  loading.value = true
  const { data, response } = await getDataSettingsApiV1SettingsDataGet({
    client,
    query: { cluster_id: clusterId },
  })
  loading.value = false
  failed.value = !response?.ok || !data
  if (failed.value) {
    logger.warn('data_settings_load_failed', { status: response?.status })
    return
  }
  const body = data as unknown as {
    lifecycle: {
      retention_days: number
      max_age_days: number
      max_docs: number
      max_size_gb: number
    }
    per_cluster_override: boolean
    report_ttl_hours: number
    findings_cleanup: { cleanup_days: number }
    findings_cleanup_override: boolean
  }
  saved.value = {
    retention_days: body.lifecycle.retention_days,
    max_age_days: body.lifecycle.max_age_days,
    max_docs: body.lifecycle.max_docs,
    max_size_gb: body.lifecycle.max_size_gb,
    cleanup_days: body.findings_cleanup.cleanup_days,
    report_ttl_hours: body.report_ttl_hours,
  }
  // one toggle for the panel: "this cluster is overridden" = any override doc exists
  // (saving with it on writes per-cluster docs for every changed group)
  override.value = body.per_cluster_override || body.findings_cleanup_override
  draft.value = draftFromSettings(saved.value)
}

watch(
  () => clusterStore.selectedId,
  (id) => {
    if (id) void loadSettings(id)
  },
  { immediate: true },
)

const parsed = computed(() => parseDraft(draft.value))
const invalid = computed(() => draftInvalid(draft.value))
const dirty = computed(() => saved.value !== null && draftDirty(saved.value, draft.value))

async function save() {
  if (saved.value === null || invalid.value) return
  const p = parsed.value
  const groups = changedGroups(saved.value, draft.value)
  const clusterId = clusterStore.selectedId
  busy.value = true
  let allOk = true
  // per-cluster settings edit the doc the effective read served (the staleness editor's rule);
  // TTL is fleet-wide by design
  const clusterArg = override.value && clusterId ? { cluster_id: clusterId } : {}
  if (groups.retention) {
    const { response } = await putRetentionApiV1SettingsRetentionPut({
      client,
      body: { retention_days: p.retention_days!, ...clusterArg },
    })
    allOk &&= response?.ok ?? false
  }
  if (groups.rollover && allOk) {
    const { response } = await putRolloverApiV1SettingsRolloverPut({
      client,
      body: {
        max_age_days: p.max_age_days!,
        max_docs: p.max_docs!,
        max_size_gb: p.max_size_gb!,
        ...clusterArg,
      },
    })
    allOk &&= response?.ok ?? false
  }
  if (groups.cleanup && allOk) {
    const { response } = await putFindingsCleanupApiV1SettingsFindingsCleanupPut({
      client,
      body: { cleanup_days: p.cleanup_days!, ...clusterArg },
    })
    allOk &&= response?.ok ?? false
  }
  if (groups.ttl && allOk) {
    const { response } = await putReportTtlApiV1SettingsReportTtlPut({
      client,
      body: { hours: p.report_ttl_hours! },
    })
    allOk &&= response?.ok ?? false
  }
  busy.value = false
  if (!allOk) {
    logger.warn('data_settings_save_failed', {})
    toast.error('Saving failed. The store keeps the previous values. Reload to see what landed.')
    if (clusterId) void loadSettings(clusterId) // partial saves must not fake a clean state
    return
  }
  saved.value = {
    retention_days: p.retention_days!,
    max_age_days: p.max_age_days!,
    max_docs: p.max_docs!,
    max_size_gb: p.max_size_gb!,
    cleanup_days: p.cleanup_days!,
    report_ttl_hours: p.report_ttl_hours!,
  }
  toast.success('Data settings saved. The daily sweeps apply them on their next run')
}

function discard() {
  if (saved.value !== null) draft.value = draftFromSettings(saved.value)
}

</script>

<template>
  <div class="stack">
    <div class="scanner-banner">
      <AppIcon name="database" :size="14" />
      Retention retires whole time-partitioned indices at the horizon, never single documents.
      The daily lifecycle sweep reads these settings live, so an edit applies at its next run.
    </div>

    <NoClusterState v-if="clusterStore.none" />
    <UiSkeleton v-else-if="loading" :height="180" radius="sm" label="Loading data settings" />
    <p v-else-if="failed" class="load-error" role="alert">
      Data settings unavailable. Check the backend connection.
    </p>

    <template v-else>
      <SettingsCard
        title="Retention"
        subtitle="one window per cluster for the history data: how far back history and time travel reach"
      >
        <SettingsRow
          label="History retention"
          hint="Applies to the five history indices below. The daily sweep drops whole indices once they expire."
        >
          <SettingsInput
            id="ret-days"
            v-model="draft.retention"
            num
            unit="days"
            :invalid="parsed.retention_days === null"
          />
        </SettingsRow>
        <div class="tbl-wrap fam-wrap">
        <table class="tbl tbl-dense tbl-quiet tbl-hover">
          <thead>
            <tr>
              <th>Index family</th>
              <th>Holds</th>
              <th class="r">Retention</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="fam in FAMILY_ROWS" :key="fam.pattern" class="fam-row">
              <td class="mono">{{ fam.pattern }}</td>
              <td class="fam-note">{{ fam.purpose }}</td>
              <td class="r">
                <span v-if="fam.kind === 'append'" class="fam-window"
                  >{{ parsed.retention_days ?? saved?.retention_days }} days</span
                >
                <span v-else class="fam-guard" :title="fam.why">
                  <DotWord tone="muted" label="protected" />
                  <AppIcon name="info" :size="12" />
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
        <p class="fam-why-note">
          <b>Why one window, not per-family?</b> Time-travel rebuilds any past moment from
          occurrences, images and inventory runs <em>together</em>, so the app only reaches as
          far back as the <em>shortest</em> window. Separate per-family windows would silently
          truncate reach to the minimum while still paying storage for the rest. They are
          planned post-MVP. Protected families take no retention window at all: hover a
          <em>protected</em> tag for why.
        </p>
        <p class="scope-src">
          {{
            override
              ? "Editing THIS cluster's override. The fleet default stays untouched."
              : 'Editing the fleet-wide default (no override exists for this cluster).'
          }}
        </p>
      </SettingsCard>

      <SettingsCard
        title="Rollover thresholds"
        subtitle="when a write index rolls to a new one, whichever trips first"
      >
        <div class="roll-grid">
          <SettingsRow label="Max age" stack>
            <SettingsInput
              id="roll-age"
              v-model="draft.maxAge"
              num
              unit="days"
              :invalid="parsed.max_age_days === null"
            />
          </SettingsRow>
          <SettingsRow label="Max docs" stack>
            <SettingsInput
              id="roll-docs"
              v-model="draft.maxDocs"
              num
              unit="docs"
              :invalid="parsed.max_docs === null"
            />
          </SettingsRow>
          <SettingsRow label="Max primary size" stack>
            <SettingsInput
              id="roll-size"
              v-model="draft.maxSize"
              num
              unit="GB"
              :invalid="parsed.max_size_gb === null"
            />
          </SettingsRow>
        </div>
      </SettingsCard>

      <SettingsCard
        title="Cleanup & report retention"
        subtitle="fleet-wide windows, independent of the per-cluster retention above"
      >
        <SettingsRow
          label="Findings cleanup window"
          hint="Cache rows whose image has been gone this long are deleted (history is untouched). Follows the per-cluster override toggle: each cluster can carry its own window."
        >
          <SettingsInput
            id="cleanup-days"
            v-model="draft.cleanup"
            num
            unit="days"
            :invalid="parsed.cleanup_days === null"
          />
        </SettingsRow>
        <SettingsRow
          label="Report/export retention"
          hint="A completed export is deleted this long after it finishes; a download past it returns 410."
        >
          <SettingsInput
            id="report-ttl"
            v-model="draft.ttl"
            num
            unit="hours"
            :invalid="parsed.report_ttl_hours === null"
          />
        </SettingsRow>
      </SettingsCard>
    </template>

    <SnapshotsCard />

    <OpensearchRuntimeCard />

    <SaveBar
      v-if="!loading && !failed"
      :dirty="dirty"
      :invalid="invalid"
      :busy="busy"
      @save="save"
      @discard="discard"
    />

  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.scanner-banner {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: var(--text-sweep-strong);
  color: var(--ink);
  background: var(--note-info-bg);
  border: 1px solid var(--note-info-line);
  border-radius: 9px;
  padding: 9px 12px;
  line-height: 1.45;
}
.scanner-banner svg {
  flex: none;
  color: var(--teal);
}
/* in-card tables run FULL-BLEED to the card edges (the ui.nuxt/GitHub settings grammar,
   operator 2026-07-16): the card is the container — a bordered box floating inside a padded
   card reads as border-in-border. The card's 16px side padding is cancelled, the head band
   spans edge to edge, and only hairlines separate the table from the card body. */
/* the preceding set-row already draws the hairline — the table adds NO top border of its
   own (the head band's color shift is the opening cue); a bottom hairline only where prose
   follows the table (fam), never against the card's own edge (snap runs flush) */
.fam-wrap {
  /* flush under the retention row: its hairline becomes the band's top edge, not a floating bar */
  margin: 0 -16px;
  border: 0;
  border-bottom: 1px solid var(--line);
  border-radius: 0;
  box-shadow: none;
}
.fam-note {
  color: var(--soft);
}
.fam-window {
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.fam-guard {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  cursor: help;
}
.fam-guard svg {
  color: var(--soft);
}
.fam-why-note,
.scope-src {
  margin: 10px 0 2px;
  font-size: var(--text-sm);
  color: var(--soft);
}
/* rollover: three small numbers earn one row, not three full-width ones */
.roll-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 18px;
}
.roll-grid :deep(.set-row) {
  border-bottom: 0;
}
@media (max-width: 720px) {
  .roll-grid {
    grid-template-columns: 1fr;
  }
}
.load-error {
  margin: 14px 0 8px;
}
</style>

<script setup lang="ts">
/**
 * Scanning panel (§13.2, C-4/D41): the ONE editable control here is the two-timer staleness
 * editor (FR-6/D20 — backend shipped in M3, the PUT is this bolt's); everything else is
 * read-only display — per-scanner cards with running version, vuln-DB provenance and the
 * effective tuning/scope from the D44 `effective_config` stamp (the same M8c provenance read
 * scanner-status uses). No version picker, no editable schedule/tuning (dropped by ruling,
 * table rows 15/17/18). The banner-behavior preview derives live from the draft values.
 */
import { computed, ref, watch } from 'vue'

import {
  getStalenessApiV1SettingsStalenessGet,
  putStalenessApiV1SettingsStalenessPut,
  scannerProvenanceApiV1ScannersProvenanceGet,
} from '@/api/generated'
import { client } from '@/api/client'
import ScannerConfigCard, {
  type EffectiveConfig,
} from '@/components/settings/ScannerConfigCard.vue'
import SaveBar from '@/components/settings/SaveBar.vue'
import NoClusterState from '@/components/settings/NoClusterState.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import { useStalenessStore } from '@/stores/staleness'
import { useToastStore } from '@/stores/toast'

import { parseWindow } from './slaForm'

interface ProvenanceCardRow {
  scanner: string
  scanner_version?: string | null
  scanner_db_version?: string | null
  scanner_db_built?: string | null
  effective_config?: EffectiveConfig | null
}

const clusterStore = useClusterStore()
const toast = useToastStore()

// ── staleness timers (the one editable control) ─────────────────────────────────────────
const savedTimers = ref<{ freshness_days: number; scanner_down_days: number } | null>(null)
const override = ref(false)
const draftN = ref('')
const draftM = ref('')
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

// ── read-only provenance cards ──────────────────────────────────────────────────────────
const scanners = ref<ProvenanceCardRow[]>([])

watch(
  () => clusterStore.selectedId,
  async (id) => {
    if (!id) return
    loading.value = true
    const [timers, prov] = await Promise.all([
      getStalenessApiV1SettingsStalenessGet({ client, query: { cluster_id: id } }),
      scannerProvenanceApiV1ScannersProvenanceGet({
        client,
        query: { cluster_id: id, runs: 1 } as never,
      }),
    ])
    loading.value = false
    failed.value = !timers.response?.ok || !timers.data
    if (failed.value) {
      logger.warn('staleness_load_failed', { status: timers.response?.status })
      return
    }
    const body = timers.data as {
      staleness: { freshness_days: number; scanner_down_days: number }
      per_cluster_override: boolean
    }
    savedTimers.value = body.staleness
    override.value = body.per_cluster_override
    draftN.value = String(body.staleness.freshness_days)
    draftM.value = String(body.staleness.scanner_down_days)
    // the cards are display-only — a failed read just renders none (scanner-status owns health)
    scanners.value = prov.response?.ok && prov.data
      ? ((prov.data as { scanners: ProvenanceCardRow[] }).scanners ?? [])
      : []
  },
  { immediate: true },
)

const parsedN = computed(() => parseWindow(draftN.value))
const parsedM = computed(() => parseWindow(draftM.value))
const invalid = computed(
  () =>
    parsedN.value === null ||
    parsedM.value === null ||
    // the escalation window engulfing the freshness window would invert the D20 hold semantics
    parsedM.value < parsedN.value,
)
const dirty = computed(
  () =>
    savedTimers.value !== null &&
    (parsedN.value !== savedTimers.value.freshness_days ||
      parsedM.value !== savedTimers.value.scanner_down_days),
)

async function save() {
  if (parsedN.value === null || parsedM.value === null) return
  busy.value = true
  const { response } = await putStalenessApiV1SettingsStalenessPut({
    client,
    body: {
      freshness_days: parsedN.value,
      scanner_down_days: parsedM.value,
      // an existing override is what the effective read served — keep editing THAT doc;
      // otherwise the edit targets the fleet-wide default (FR-6)
      ...(override.value && clusterStore.selectedId
        ? { cluster_id: clusterStore.selectedId }
        : {}),
    },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('staleness_save_failed', { status: response?.status })
    toast.error(
      response?.status === 403
        ? 'Saving needs the can_manage_settings capability.'
        : 'Saving the timers failed. The sweep keeps the current ones.',
    )
    return
  }
  savedTimers.value = { freshness_days: parsedN.value, scanner_down_days: parsedM.value }
  // the freshness banner thresholds on these timers live — drop its cache so it re-reads
  useStalenessStore().invalidate()
  toast.success('Staleness timers saved. The next daily sweep applies them')
  // the scanner-down timer bounds the retirement window: the countdown banner re-reads it
  await clusterStore.refresh()
}

function discard() {
  if (savedTimers.value === null) return
  draftN.value = String(savedTimers.value.freshness_days)
  draftM.value = String(savedTimers.value.scanner_down_days)
}
</script>

<template>
  <div class="stack">
    <div class="scanner-banner">
      <AppIcon name="layers" :size="14" />
      Both scanners run every cycle, results kept <b>per-scanner</b> and never merged:
      dashboards facet by scanner to avoid double-counting.
    </div>

    <SettingsCard
      title="Staleness timers"
      subtitle="the two-timer model: drives the stale state and the inventory banners"
    >
      <NoClusterState v-if="clusterStore.none" />
      <UiSkeleton
        v-else-if="loading"
        :height="180"
        radius="sm"
        label="Loading timers"
        class="skel-gap"
      />
      <p v-else-if="failed" class="load-error" role="alert">
        Staleness timers unavailable. Check the backend connection.
      </p>
      <template v-else>
        <SettingsRow
          label="Per-finding freshness"
          hint="A finding not re-seen within this window goes stale."
        >
          <SettingsInput
            id="stale-n"
            v-model="draftN"
            num
            unit="days"
            :invalid="parsedN === null"
          />
        </SettingsRow>
        <SettingsRow
          label="Scanner-down escalation"
          hint="A scanner silent this long stales ALL its findings. Must not undercut the freshness window."
        >
          <SettingsInput
            id="stale-m"
            v-model="draftM"
            num
            unit="days"
            :invalid="parsedM === null || (parsedN !== null && parsedM !== null && parsedM < parsedN)"
          />
        </SettingsRow>
        <div class="stale-note">
          <AppIcon name="info" :size="13" />
          <span v-if="parsedN !== null && parsedM !== null && parsedM >= parsedN">
            Preview: a finding unseen for <b>{{ parsedN }}d</b> goes stale, but between
            <b>{{ parsedN }}d</b> and <b>{{ parsedM }}d</b> of scanner silence the per-finding
            timer is <b>held</b> (a brief outage won't mass-stale everything) and the inventory
            shows a "scanner silent" banner; past <b>{{ parsedM }}d</b> every finding of that
            scanner is stale. Editing timers never deletes anything: stale is only a flag. Findings are deleted only by the
            cleanup window in Data &amp; OpenSearch, once their image has been gone that long.
          </span>
          <span v-else>Both windows must be positive, with escalation ≥ freshness.</span>
        </div>
        <p class="scope-src">
          {{
            override
              ? 'Editing THIS cluster\'s override. The fleet default stays untouched.'
              : 'Editing the fleet-wide default (no override exists for this cluster).'
          }}
        </p>
      </template>
    </SettingsCard>

    <SaveBar
      v-if="!loading && !failed"
      :dirty="dirty"
      :invalid="invalid"
      :busy="busy"
      @save="save"
      @discard="discard"
    />

    <ScannerConfigCard
      v-for="s in scanners"
      :key="s.scanner"
      :scanner="s.scanner"
      :version="s.scanner_version ?? null"
      :db-version="s.scanner_db_version ?? null"
      :db-built="s.scanner_db_built ?? null"
      :config="s.effective_config ?? null"
    />
  </div>
</template>

<style scoped>
.stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
/* the prototype .scanner-banner grammar, ink prose per DESIGN.md §2 */
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
.stale-note {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: var(--text-sweep-strong);
  color: var(--ink);
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: 9px;
  padding: 9px 12px;
  line-height: 1.45;
  margin-top: 14px;
}
.stale-note svg {
  flex: none;
  color: var(--teal);
}
.scope-src {
  margin: 10px 0 2px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.load-error {
  margin: 14px 0 8px;
}
.skel-gap {
  margin: 14px 0 8px;
}
</style>

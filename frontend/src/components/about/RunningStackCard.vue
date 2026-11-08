<script setup lang="ts">
/**
 * Running stack (issue 341): what this install runs, for the About page. Self-contained: it owns
 * its two reads (`/api/v1/meta`, the selected cluster's scanner provenance) and their loading,
 * empty and error states. Rows use the settings row grammar (label + hint left, value right),
 * grouped in the Framework7 list manner. "Copy diagnostics" puts the same facts on the clipboard
 * as plain text for a bug report.
 */
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { buildDiagnostics, readFailureCopy, type RunningMeta } from '@/about/diagnostics'
import { client } from '@/api/client'
import { getMetaApiV1MetaGet, scannerProvenanceApiV1ScannersProvenanceGet } from '@/api/generated'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import type { ProvenanceRow } from '@/components/scanners/ScannerStatusCard.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsRow from '@/components/settings/SettingsRow.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'
import { lastDataAt } from '@/system/freshness'
import { APP_VERSION } from '@/version'

const props = defineProps<{ clusterId: string | null; clusterName?: string | null }>()

const toast = useToastStore()

const meta = ref<RunningMeta | null>(null)
const metaLoading = ref(true)
const metaError = ref<string | null>(null)

const scanners = ref<ProvenanceRow[]>([])
const provLoading = ref(false)
const provError = ref<string | null>(null)

async function loadMeta() {
  const { data, response } = await getMetaApiV1MetaGet({ client })
  metaLoading.value = false
  if (!response?.ok || !data) {
    metaError.value = readFailureCopy(response?.status)
    logger.warn('about_meta_failed', { status: response?.status })
    return
  }
  meta.value = data as RunningMeta
}
void loadMeta()

watch(
  () => props.clusterId,
  async (id) => {
    scanners.value = []
    provError.value = null
    if (!id) return
    provLoading.value = true
    const { data, response } = await scannerProvenanceApiV1ScannersProvenanceGet({
      client,
      query: { cluster_id: id, runs: 1 } as never,
    })
    if (id !== props.clusterId) return // the selection moved on while this read was in flight
    provLoading.value = false
    if (!response?.ok || !data) {
      provError.value = readFailureCopy(response?.status)
      logger.warn('about_provenance_failed', { status: response?.status })
      return
    }
    scanners.value = (data as { scanners: ProvenanceRow[] }).scanners ?? []
  },
  { immediate: true },
)

const installRows = computed(() => {
  const m = meta.value
  return [
    { label: 'JAVV release', hint: 'the backend build answering this page', value: m && `v${m.version}` },
    {
      label: 'Store schema',
      hint: 'index layout version; the backend upgrades it at startup',
      value: m && `v${m.mapping_version}`,
    },
    {
      label: 'Scanner report formats',
      hint: 'report versions the backend accepts from scanners',
      value: m && m.envelope_versions.map((v) => `v${v}`).join(', '),
    },
    { label: 'OpenSearch', hint: 'read live from the store', value: m && (m.opensearch_version ?? 'unavailable') },
    { label: 'Python', hint: 'the backend runtime', value: m && m.python_version },
  ]
})

const clusterLabel = computed(() => props.clusterName || props.clusterId)

async function copyDiagnostics() {
  const text = buildDiagnostics({
    meta: meta.value,
    frontendVersion: APP_VERSION,
    cluster: props.clusterId ? { id: props.clusterId, name: clusterLabel.value ?? props.clusterId } : null,
    scanners: scanners.value,
    userAgent: navigator.userAgent,
    now: new Date(),
  })
  try {
    // absent outside a secure context (plain http on a non-localhost host)
    if (!navigator.clipboard) throw new DOMException('no clipboard', 'NotSupportedError')
    await navigator.clipboard.writeText(text)
    toast.success('Diagnostics copied. Paste them into your bug report.')
  } catch (exc) {
    const reason = exc instanceof DOMException ? exc.name : 'unknown'
    logger.warn('diagnostics_copy_failed', { reason })
    toast.error("Couldn't copy the diagnostics: the browser blocked the clipboard.")
  }
}
</script>

<template>
  <SettingsCard title="Running stack" subtitle="read live from this install; nothing here is typed in">
    <template #action>
      <UiButton variant="control" class="stack-copy" @click="copyDiagnostics">Copy diagnostics</UiButton>
    </template>

    <div class="stack-group stack-install">
      <div class="stack-group-title">This install</div>
      <UiSkeleton v-if="metaLoading" :height="176" label="Loading the running versions" />
      <template v-else>
        <p v-if="metaError" class="stack-error" role="alert">{{ metaError }}</p>
        <template v-else>
          <SettingsRow
            v-for="row in installRows"
            :key="row.label"
            class="stack-row"
            :label="row.label"
            :hint="row.hint"
          >
            <span class="stack-value" :class="{ 'stack-value-missing': row.value === 'unavailable' }">{{
              row.value
            }}</span>
          </SettingsRow>
        </template>
      </template>
      <!-- known locally, so it shows even when the backend read fails -->
      <SettingsRow class="stack-row" label="Frontend build" hint="this page's own build; matches the release except mid-rollout">
        <span class="stack-value">v{{ APP_VERSION }}</span>
      </SettingsRow>
    </div>

    <div class="stack-group stack-scanners">
      <div class="stack-group-title">
        Scanners<template v-if="clusterLabel"> · <span class="stack-cluster">{{ clusterLabel }}</span></template>
      </div>
      <p v-if="!clusterId" class="stack-empty">Select a cluster in the top bar to see its scanners.</p>
      <UiSkeleton v-else-if="provLoading" :height="96" label="Loading the scanner versions" />
      <p v-else-if="provError" class="stack-error" role="alert">{{ provError }}</p>
      <p v-else-if="!scanners.length" class="stack-empty">
        No committed scan for this cluster yet, so no scanner version is known.
      </p>
      <template v-else>
        <SettingsRow v-for="s in scanners" :key="s.scanner" class="stack-row">
          <template #label><ScannerTag :name="s.scanner" /></template>
          <div class="stack-scanner-value">
            <span class="stack-value">{{ s.scanner_version ? `v${s.scanner_version}` : 'unknown' }}</span>
            <span class="stack-db"
              >vulnerability database {{ s.scanner_db_version ?? 'unknown' }} · built
              <span :title="s.scanner_db_built ?? ''">{{ lastDataAt(s.scanner_db_built ?? null) }}</span></span
            >
          </div>
        </SettingsRow>
      </template>
      <RouterLink to="/scanner-status" class="stack-link">
        Scanner status <AppIcon name="chevron" :size="12" />
      </RouterLink>
    </div>
  </SettingsCard>
</template>

<style scoped>
.stack-group + .stack-group {
  margin-top: var(--space-4);
}
.stack-group-title {
  padding: 12px 0 2px;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--soft);
}
/* a cluster id or name is data: shown as stored, never uppercased by the group label */
.stack-cluster {
  text-transform: none;
  letter-spacing: 0.02em;
}
.stack-value {
  font-family: var(--font-mono);
  font-size: var(--text-mono-cell);
  color: var(--ink);
}
.stack-value-missing {
  color: var(--soft);
}
.stack-error,
.stack-empty {
  margin: 10px 0 4px;
  font-size: var(--text-sm);
}
.stack-error {
  color: var(--ink);
}
.stack-empty {
  color: var(--soft);
}
.stack-scanner-value {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.stack-db {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
}
.stack-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 12px;
  padding: 4px 8px;
  margin-left: -8px;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  font-size: var(--text-sm);
  color: var(--coral-text);
  text-decoration: none;
  transition:
    background var(--dur-quick),
    border-color var(--dur-quick);
}
.stack-link:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
  text-decoration: underline;
}
.stack-link:active {
  background: var(--control-active-bg);
}
@media (prefers-reduced-motion: reduce) {
  .stack-link {
    transition: none;
  }
}
</style>

<script setup lang="ts">
/**
 * The read-only per-scanner config card (§13.2, C-4/D41): running version + vuln-DB provenance
 * + the effective tuning flags + applied scope, all from the latest COMMITTED scan-event's
 * `effective_config` stamp (D44/FR-25 — the same M8c provenance read scanner-status uses).
 * NO version picker, NO editable tuning: the version changes by swapping the published image
 * tag and tuning stays env/GitOps — hence the operator-managed affordance, not a form.
 */
import { computed } from 'vue'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import { scannerSettingLabel } from '@/lib/scannerSettingLabel'

export interface EffectiveConfig {
  tuning: Record<string, unknown>
  scope: Record<string, string[]>
}

const props = defineProps<{
  scanner: string
  version: string | null
  dbVersion: string | null
  dbBuilt: string | null
  config: EffectiveConfig | null
}>()

const scopeUnrestricted = computed(
  () =>
    props.config !== null &&
    Object.keys(SCOPE_LABEL).every((key) => !(props.config?.scope[key] ?? []).length),
)

const fmtValue = (value: unknown) =>
  value === null || value === undefined || value === '' ? '-' : String(value)

const fmtWhen = (iso: string | null) =>
  iso === null
    ? '-'
    : new Date(iso).toLocaleString('en-GB', { hour12: false, dateStyle: 'medium', timeStyle: 'short' })

const SCOPE_LABEL: Record<string, string> = {
  include_namespaces: 'include namespaces',
  ignore_namespaces: 'ignore namespaces',
  exclude_images: 'exclude images',
  ignore_kinds: 'ignore kinds',
}
</script>

<template>
  <section class="card">
    <div class="card-head">
      <div class="head-id">
        <ScannerTag :name="scanner" />
        <span v-if="version" class="mono-cell ver">v{{ version }}</span>
      </div>
      <span class="gitops-tag" title="Version and tuning change by swapping the published image tag or its environment variables, never in the app, because JAVV never changes the clusters it monitors, and every scan records the scanner version that produced it.">operator-managed (GitOps)</span>
    </div>
    <div class="card-body">
      <template v-if="config !== null">
        <div class="cfg-row">
          <span class="cfg-key">Vulnerability database schema</span>
          <span class="mono-cell sm"><template v-if="dbVersion != null">{{ dbVersion }}</template><span v-else class="muted-dash">-</span> · built {{ fmtWhen(dbBuilt) }}</span>
        </div>
        <div v-for="(value, key) in config.tuning" :key="key" class="cfg-row">
          <span class="cfg-key" :title="String(key)">{{ scannerSettingLabel(String(key)) }}</span>
          <span class="mono-cell sm">{{ fmtValue(value) }}</span>
        </div>
        <div class="cfg-scope">
          <span class="cfg-scope-title">applied scope</span>
          <template v-for="(label, key) in SCOPE_LABEL" :key="key">
            <div v-if="(config.scope[key] ?? []).length" class="cfg-row">
              <span class="cfg-key">{{ label }}</span>
              <span class="cfg-chips">
                <code v-for="item in config.scope[key]" :key="item" class="cfg-chip mono-cell">{{ item }}</code>
              </span>
            </div>
          </template>
          <p v-if="scopeUnrestricted" class="cfg-empty">
            no restrictions: the whole cluster is scanned
          </p>
        </div>
      </template>
      <p v-else class="cfg-empty">
        No committed run carries a config stamp yet. The display fills after the scanner's next
        push (schema v3+).
      </p>
    </div>
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  overflow: hidden;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--line2);
}
.head-id {
  display: inline-flex;
  align-items: center;
  gap: 9px;
}
.ver {
  font-weight: 700;
  color: var(--ink);
}
.gitops-tag {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--soft);
  border: 1px solid var(--line);
  padding: 3px 8px;
  border-radius: 5px;
  flex: none;
}
.card-body {
  padding: 6px 16px 12px;
}
.cfg-row {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 7px 0;
  border-bottom: 1px solid var(--line2);
}
.cfg-row:last-child {
  border-bottom: 0;
}
.cfg-key {
  flex: none;
  width: 200px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.cfg-scope {
  margin-top: 6px;
}
.cfg-scope-title {
  display: block;
  padding-top: 8px;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--soft);
}
.cfg-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.cfg-chip {
  padding: 2px 7px;
  background: var(--panel);
  border: 1px solid var(--line2);
  border-radius: 5px;
  font-size: var(--text-sm);
  color: var(--ink);
}
.cfg-empty {
  margin: 8px 0 2px;
  font-size: var(--text-sm);
  color: var(--soft);
}
</style>

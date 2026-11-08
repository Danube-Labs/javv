<script setup lang="ts">
/**
 * OpenSearch runtime card (§D ruling) — read-only display of the backend's allowlist-shaped
 * proxy read: the stat band (version / cluster health / topology) flush under the card head,
 * then one quiet-table row per node. Renders nothing until the read lands (optional context,
 * never a scary error).
 */
import { ref } from 'vue'

import { getOpensearchRuntimeApiV1AdminOpensearchRuntimeGet } from '@/api/generated'
import { client } from '@/api/client'
import DotWord from '@/components/chips/DotWord.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import { logger } from '@/lib/logger'

interface RuntimeNode {
  name: string | null
  roles: string[]
  heap_used_mb: number
  heap_max_mb: number
  discovery_type: string | null
  path_repo: string | null
  security_enabled: boolean
}

interface Runtime {
  version: string | null
  distribution: string | null
  cluster_name: string | null
  status: string | null
  number_of_nodes: number
  active_shards: number
  nodes: RuntimeNode[]
}

const runtime = ref<Runtime | null>(null)

async function load() {
  const { data, response } = await getOpensearchRuntimeApiV1AdminOpensearchRuntimeGet({ client })
  if (!response?.ok || !data) {
    logger.warn('opensearch_runtime_load_failed', { status: response?.status })
    return
  }
  runtime.value = data as unknown as Runtime
}
void load()

function healthTone(status: string | null): 'ok' | 'warn' | 'down' | 'muted' {
  if (status === 'green') return 'ok'
  if (status === 'yellow') return 'warn'
  if (status === 'red') return 'down'
  return 'muted'
}
</script>

<template>
  <SettingsCard
    v-if="runtime"
    title="OpenSearch runtime"
    subtitle="read-only: the install of JAVV sets these settings, and the card shows each one that it can read"
  >
    <div class="stat-band stat-band--stat rt-band">
      <div class="stat-cell">
        <span class="stat-label">Version</span>
        <span class="stat-num">{{ runtime.distribution }} {{ runtime.version }}</span>
      </div>
      <div class="stat-cell">
        <span class="stat-label">Cluster</span>
        <span class="stat-num">{{ runtime.cluster_name }}</span>
        <span class="stat-sub">
          <DotWord :tone="healthTone(runtime.status)" :label="runtime.status ?? 'unknown'" />
        </span>
      </div>
      <div class="stat-cell">
        <span class="stat-label">Topology</span>
        <span class="stat-num"
          >{{ runtime.number_of_nodes }}
          {{ runtime.number_of_nodes === 1 ? 'node' : 'nodes' }}</span
        >
        <span class="stat-sub">{{ runtime.active_shards }} active shards</span>
      </div>
    </div>
    <div class="tbl-wrap rt-wrap">
      <table class="tbl tbl-dense tbl-quiet tbl-hover">
        <thead>
          <tr>
            <th>Node</th>
            <th>Roles</th>
            <th class="r">JVM heap</th>
            <th>Discovery</th>
            <th>Snapshot path</th>
            <th>Security</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="n in runtime.nodes" :key="n.name ?? ''">
            <td class="mono">{{ n.name }}</td>
            <td><template v-if="n.roles.length">{{ n.roles.join(', ') }}</template><span v-else class="muted-dash">-</span></td>
            <td class="mono r">{{ n.heap_used_mb }} / {{ n.heap_max_mb }} MB</td>
            <td class="mono"><template v-if="n.discovery_type != null">{{ n.discovery_type }}</template><span v-else class="muted-dash">-</span></td>
            <td class="mono">{{ n.path_repo ?? 'unset' }}</td>
            <td>{{ n.security_enabled ? 'enabled' : 'disabled' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </SettingsCard>
</template>

<style scoped>
/* the cluster facts ride the shared stat-band, full-bleed and FLUSH under the card head —
   the head's own hairline is the only separator (no border + gap + border stacks) */
.rt-band {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: -4px -16px 0;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}
.rt-wrap {
  margin: 0 -16px -14px;
  border: 0;
  border-top: 1px solid var(--line);
  border-radius: 0;
  box-shadow: none;
}
</style>

/**
 * Cluster context: the registry list (M8c, display names from system-config) + the selected
 * `cluster_id` — the tenant key every data read carries (D38/H9). Selection
 * persists per browser; `cluster_id` (immutable) is the key, never the relabelable name.
 */
import { defineStore } from 'pinia'

import { client } from '@/api/client'
import { listClustersApiV1ClustersGet } from '@/api/generated'
import type { RetirementSchedule } from '@/system/retirement'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

export interface ClusterEntry extends RetirementSchedule {
  cluster_id: string
  cluster_name: string
}

const STORAGE_KEY = 'javv.selected_cluster_id'

let refreshSeq = 0

export const useClusterStore = defineStore('cluster', {
  state: () => ({
    clusters: [] as ClusterEntry[],
    selectedId: null as string | null,
    loaded: false,
    failed: false,
  }),
  getters: {
    selected: (s) => s.clusters.find((c) => c.cluster_id === s.selectedId) ?? null,
    /** The list answered and is empty: per-cluster reads have no id to send. */
    none: (s) => s.loaded && !s.failed && s.clusters.length === 0,
  },
  actions: {
    /** `preferredId` = a deep link's `?cluster=` (issue 433). Precedence: valid link > remembered
     * selection > first cluster. A link's choice is deliberately NOT persisted — opening a
     * colleague's beta link must not flip this browser's default; an unknown id falls back
     * loudly (toast) instead of rendering an empty app. */
    async fetchClusters(preferredId: string | null = null): Promise<void> {
      const { data, response } = await listClustersApiV1ClustersGet({ client })
      if (response?.ok && data) {
        this.clusters = (data as { clusters: ClusterEntry[] }).clusters ?? []
        const known = (id: string | null): id is string =>
          id !== null && this.clusters.some((c) => c.cluster_id === id)
        if (preferredId !== null && !known(preferredId)) {
          useToastStore().info('The link points at a cluster this store does not know. Showing your default.')
          logger.warn('url_cluster_unknown', { cluster_id: preferredId })
        }
        const remembered = localStorage.getItem(STORAGE_KEY)
        this.selectedId = known(preferredId)
          ? preferredId
          : known(remembered)
            ? remembered
            : (this.clusters[0]?.cluster_id ?? null)
        this.failed = false
      } else {
        // silence-is-a-bug (audit 343): without the registry every screen renders empty —
        // the shell shows the alert off this flag
        this.failed = true
        logger.warn('clusters_fetch_failed', { status: response?.status })
      }
      this.loaded = true
    },
    /** Re-read the list and keep the selection while its cluster is still listed. A cluster
     * retired meanwhile falls back as at load, with a toast, since every screen re-scopes
     * (`quiet`: the caller retired it and says so itself). For the countdown banner's poll and
     * the Settings writes that move a schedule or the list. Unlike `fetchClusters`, it never
     * trades a deep-linked selection for the remembered one. Only the newest call applies: a
     * poll answered after a later write's re-read is dropped. */
    async refresh({ quiet = false } = {}): Promise<void> {
      const seq = ++refreshSeq
      const { data, response } = await listClustersApiV1ClustersGet({ client })
      if (seq !== refreshSeq) return
      if (!response?.ok || !data) {
        logger.warn('clusters_refresh_failed', { status: response?.status })
        return
      }
      const was = this.selected
      this.clusters = (data as { clusters: ClusterEntry[] }).clusters ?? []
      this.failed = false
      const known = (id: string | null): id is string =>
        id !== null && this.clusters.some((c) => c.cluster_id === id)
      if (known(this.selectedId)) return
      const remembered = localStorage.getItem(STORAGE_KEY)
      this.selectedId = known(remembered) ? remembered : (this.clusters[0]?.cluster_id ?? null)
      if (was && !quiet) {
        const now = this.selected?.cluster_name
        useToastStore().info(
          now
            ? `${was.cluster_name} is no longer on the cluster list. Showing ${now}.`
            : `${was.cluster_name} is no longer on the cluster list.`,
        )
      }
    },
    select(clusterId: string) {
      this.selectedId = clusterId
      localStorage.setItem(STORAGE_KEY, clusterId)
    },
  },
})

/**
 * Cluster retirement in Settings (issue 765): the fleet listing with retired clusters included,
 * and retire / un-retire. The schedule dates come from the backend (`GET /api/v1/clusters`),
 * which applies each cluster's own window; nothing here re-derives one.
 */
import { ref } from 'vue'

import { client } from '@/api/client'
import {
  listClustersApiV1ClustersGet,
  retireApiV1ClustersClusterIdRetirePost,
  unretireApiV1ClustersClusterIdUnretirePost,
} from '@/api/generated'
import { DELETE_UNFINISHED_TYPE } from '@/api/problem'
import { logger } from '@/lib/logger'

export interface FleetCluster {
  cluster_id: string
  cluster_name: string
  retired: boolean
  last_scan_at: string | null
  silent_since: string | null
  warns_at: string | null
  retires_at: string | null
  delete_started: boolean
  retirement_mode: 'manual' | 'auto' | null
}

export function useFleetClusters() {
  const rows = ref<FleetCluster[]>([])
  const loading = ref(true)
  const failed = ref(false)

  async function load(): Promise<void> {
    loading.value = true
    const { data, response } = await listClustersApiV1ClustersGet({
      client,
      query: { include_retired: true },
    })
    loading.value = false
    failed.value = !response?.ok || !data
    if (failed.value) {
      logger.warn('fleet_clusters_load_failed', { status: response?.status })
      return
    }
    rows.value = (data as { clusters: FleetCluster[] }).clusters ?? []
  }

  /** null on success, else the message to show. */
  async function retire(clusterId: string): Promise<string | null> {
    const { response } = await retireApiV1ClustersClusterIdRetirePost({
      client,
      path: { cluster_id: clusterId },
    })
    if (response?.ok) return null
    logger.warn('cluster_retire_failed', { status: response?.status })
    if (response?.status === 409) return 'It is already retired.'
    if (response?.status === 403) return 'Retiring a cluster needs the can_manage_settings capability.'
    return 'Retiring failed. The cluster is unchanged.'
  }

  async function unretire(clusterId: string): Promise<string | null> {
    const { response, error } = await unretireApiV1ClustersClusterIdUnretirePost({
      client,
      path: { cluster_id: clusterId },
    })
    if (response?.ok) return null
    logger.warn('cluster_unretire_failed', { status: response?.status })
    // a delete started since the list was read (issue 778): its tokens and part of its data are gone
    if (response?.status === 409 && (error as { type?: unknown } | undefined)?.type === DELETE_UNFINISHED_TYPE)
      return 'Its delete did not finish. Delete it again.'
    if (response?.status === 409) return 'It is not retired any more.'
    if (response?.status === 403) return 'Bringing a cluster back needs the can_manage_settings capability.'
    return 'Bringing it back failed. The cluster stays retired.'
  }

  return { rows, loading, failed, load, retire, unretire }
}

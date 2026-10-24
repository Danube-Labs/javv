/**
 * The findings facets a panel counts from. A screen that already holds them passes them in
 * (Overview reads them once for all its panels, so its numbers cannot disagree); a panel on a
 * dashboard gets none and reads them itself for the dashboard's cluster and T. Panels that ask
 * for the same query while that read is open share it, so a dashboard with three facet panels
 * sends one request (DESIGN.md §10).
 */
import { computed, ref, watch, type ComputedRef } from 'vue'

import { client } from '@/api/client'
import { facetFindingsApiV1FindingsFacetsGet } from '@/api/generated'
import { logger } from '@/lib/logger'
import type { FacetBucket } from '@/stores/overview'

export type Facets = Record<string, FacetBucket[]>
export interface FacetsQuery {
  cluster_id: string
  as_of?: string
}

type Read = { facets: Facets } | { failed: number | null }
const open = new Map<string, Promise<Read>>()

async function readFacets(query: FacetsQuery): Promise<Read> {
  const { data, response } = await facetFindingsApiV1FindingsFacetsGet({ client, query: query as never })
  if (!response?.ok || !data) return { failed: response?.status ?? null }
  return { facets: (data as { facets?: Facets }).facets ?? {} }
}

/** One read per query while it is open; the next ask after it lands reads again. */
function sharedRead(query: FacetsQuery): Promise<Read> {
  const key = JSON.stringify([query.cluster_id, query.as_of ?? null])
  let read = open.get(key)
  if (!read) {
    read = readFacets(query).finally(() => open.delete(key))
    open.set(key, read)
  }
  return read
}

export function useFindingsFacets(
  given: () => Facets | undefined,
  query: () => FacetsQuery | null | undefined,
): { facets: ComputedRef<Facets>; settled: ComputedRef<boolean>; failed: ComputedRef<boolean> } {
  const own = ref<Facets>({})
  const ownSettled = ref(false)
  const failed = ref(false)

  let seq = 0
  watch(
    () => (given() === undefined ? query() : null),
    async (q, old) => {
      if (!q) return
      const mine = ++seq
      if (old && old.cluster_id !== q.cluster_id) {
        ownSettled.value = false // another tenant's counts would be a lie
        own.value = {}
      }
      const read = await sharedRead(q)
      if (mine !== seq) return // a newer read owns the panel now
      failed.value = 'failed' in read
      if ('failed' in read) logger.warn('findings_facets_failed', { status: read.failed })
      else own.value = read.facets
      ownSettled.value = true
    },
    { immediate: true, deep: true },
  )

  return {
    facets: computed(() => given() ?? own.value),
    settled: computed(() => given() !== undefined || ownSettled.value),
    failed: computed(() => given() === undefined && failed.value),
  }
}

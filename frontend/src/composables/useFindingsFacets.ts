/**
 * The findings facets a panel counts from. A screen that already holds them passes them in
 * (Overview reads them once for all its panels, so its numbers cannot disagree); a panel on a
 * dashboard gets none and reads them itself for the dashboard's cluster and T. Panels that ask
 * for the same query while that read is open share it, so a dashboard with three facet panels
 * sends one request (DESIGN.md §10). The query is the whole request, the filters of a panel
 * too (issue 999): two panels with different filters must not share counts.
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
  /** the /findings filters of a dashboard panel, and `all_filters` with them */
  [param: string]: unknown
}

type Read = { facets: Facets } | { failed: number | null }
const open = new Map<string, Promise<Read>>()

async function readFacets(query: FacetsQuery): Promise<Read> {
  const { data, response } = await facetFindingsApiV1FindingsFacetsGet({ client, query: query as never })
  if (!response?.ok || !data) {
    // once per read, however many panels share it
    logger.warn('findings_facets_failed', { status: response?.status })
    return { failed: response?.status ?? null }
  }
  return { facets: (data as { facets?: Facets }).facets ?? {} }
}

/** A value key of the whole query: equal queries give one key, whatever their key order. An
 * undefined param is not sent, so it is not in the key. */
function queryKey(query: FacetsQuery): string {
  return JSON.stringify(
    Object.keys(query)
      .filter((k) => query[k] !== undefined)
      .sort()
      .map((k) => [k, query[k]]),
  )
}

/** One read per query while it is open; the next ask after it lands reads again. */
function sharedRead(key: string, query: FacetsQuery): Promise<Read> {
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

  /** the cluster the counts on screen belong to: another tenant's counts would be a lie */
  let ownFor: string | null = null
  let seq = 0
  watch(
    () => {
      const q = given() === undefined ? query() : null
      // a value key: a host that rebuilds an equal query object starts no new read
      return q ? queryKey(q) : null
    },
    async (key) => {
      const mine = ++seq // also when no read starts: an older read in flight must not land
      if (!key) return
      const q = Object.fromEntries(JSON.parse(key) as [string, unknown][]) as FacetsQuery
      if (q.cluster_id !== ownFor) {
        ownSettled.value = false
        own.value = {}
        ownFor = q.cluster_id
      }
      const read = await sharedRead(key, q)
      if (mine !== seq) return // a newer read owns the panel now
      failed.value = 'failed' in read
      if (!('failed' in read)) own.value = read.facets
      ownSettled.value = true
    },
    { immediate: true },
  )

  return {
    facets: computed(() => given() ?? own.value),
    settled: computed(() => given() !== undefined || ownSettled.value),
    failed: computed(() => given() === undefined && failed.value),
  }
}

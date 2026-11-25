/** Overview dashboard state (M9c slice 1) — every number is a SERVER aggregation (facets,
 * trends, freshness); this store only holds what the server returned, keyed by the global
 * cluster + T (D28 rewind rides in via the callers' `withGlobals`). */
import { defineStore } from 'pinia'

import { client } from '@/api/client'
import {
  facetFindingsApiV1FindingsFacetsGet,
  scannerFreshnessApiV1ScannersFreshnessGet,
  findingsTrendApiV1TrendsFindingsGet,
} from '@/api/generated'
import type { FindingsTrendData } from '@/charts/buildFindingsTrendOption'
import { buildDailyTrendQuery } from '@/charts/buildTrendQuery'
import { logger } from '@/lib/logger'

export interface FacetBucket {
  key: string
  count: number
  by_scanner: Record<string, number>
}
type Facets = Record<string, FacetBucket[]>

export const useOverviewStore = defineStore('overview', {
  state: () => ({
    facets: {} as Facets,
    trend: { new: {}, resolved: {} } as FindingsTrendData,
    sevTrend: {} as Record<string, { date: string; count: number }[]>,
    sevTrendLoading: false,
    lastIngestAt: null as string | null,
    loading: false,
    failed: false,
  }),
  getters: {
    bucket: (s) => (facet: string, key: string) =>
      s.facets[facet]?.find((b) => b.key === key) ?? null,
    empty: (s) => !s.loading && (s.facets.present?.[0]?.count ?? 0) === 0,
  },
  actions: {
    /** One load per (cluster, T, window) — the view calls this from its watcher. */
    async load(params: { cluster_id: string; as_of?: string }, windowDays: number) {
      this.loading = true
      this.failed = false
      const trendQ = buildDailyTrendQuery(params.cluster_id, windowDays, params.as_of ?? null)
      const [facets, trend, fresh] = await Promise.all([
        facetFindingsApiV1FindingsFacetsGet({ client, query: params as never }),
        findingsTrendApiV1TrendsFindingsGet({ client, query: trendQ as never }),
        scannerFreshnessApiV1ScannersFreshnessGet({
          client,
          query: { cluster_id: params.cluster_id },
        }),
      ])
      this.loading = false
      if (!facets.response?.ok || !trend.response?.ok || !facets.data || !trend.data) {
        this.failed = true
        logger.warn('overview_load_failed', {
          facets: facets.response?.status,
          trend: trend.response?.status,
        })
        return
      }
      this.facets = (facets.data as { facets: Facets }).facets ?? {}
      const t = trend.data as { new?: FindingsTrendData['new']; resolved?: FindingsTrendData['resolved'] }
      this.trend = { new: t.new ?? {}, resolved: t.resolved ?? {} }
      if (fresh.response?.ok && fresh.data) {
        const rows = (fresh.data as { scanners: { last_ingest_at: string | null }[] }).scanners
        this.lastIngestAt =
          rows
            .map((r) => r.last_ingest_at)
            .filter((v): v is string => v !== null)
            .sort()
            .at(-1) ?? null
      }
    },

    /** The severity lens (1b): same window, split server-side; optional scanner scope rides
     * as a QUERY filter. Only callable at T=now (the route 422s otherwise — the view gates). */
    async loadSeverityTrend(clusterId: string, windowDays: number, scanner: 'trivy' | 'grype' | null) {
      const q = {
        ...buildDailyTrendQuery(clusterId, windowDays, null),
        split: 'severity',
        ...(scanner ? { scanner } : {}),
      }
      this.sevTrendLoading = true
      const { data, response } = await findingsTrendApiV1TrendsFindingsGet({
        client,
        query: q as never,
      })
      this.sevTrendLoading = false
      if (response?.ok && data) {
        this.sevTrend = (data as { new: Record<string, { date: string; count: number }[]> }).new ?? {}
      } else {
        logger.warn('overview_sev_trend_failed', { status: response?.status })
      }
    },
  },
})

/**
 * The Audit log counts of a filter menu outside the Audit log: the audit Filters of a dashboard
 * panel (issue 1063). The newest query owns the counts, so a slow answer to an old query never
 * shows.
 */
import { ref, watch, type Ref } from 'vue'

import { auditFacetsApiV1AuditFacetsGet } from '@/api/generated'
import type { FacetsResponse } from '@/filters/facets'
import { logger } from '@/lib/logger'

export function useAuditFacets(query: () => Record<string, unknown> | null): {
  facets: Ref<FacetsResponse>
  failed: Ref<boolean>
} {
  const facets = ref<FacetsResponse>({})
  const failed = ref(false)
  let seq = 0
  watch(
    query,
    async (q) => {
      if (!q) return
      const mine = ++seq
      const response = await auditFacetsApiV1AuditFacetsGet({ query: q as never })
      if (mine !== seq) return
      if (response.response?.ok && response.data) {
        facets.value = (response.data as { facets?: FacetsResponse }).facets ?? {}
        failed.value = false
      } else {
        failed.value = true
        logger.warn('panel_audit_facets_failed', { status: response.response?.status })
      }
    },
    { immediate: true, deep: true },
  )
  return { facets, failed }
}

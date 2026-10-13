/** Grid state for the audit table (M9d slice 1; SCREENS §10) — the same cursor-stack pager
 * as the findings grid (`useCursorPager`): no offset, no random jumps; rows/total are the
 * server's verbatim. Rows are the D32 stream, decorated at read with the touched entity's
 * identity (`finding`/`decision` sub-objects — null when the doc aged out of the store or the
 * event was a bulk marker). */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { useCursorPager } from '@/composables/useCursorPager'

export interface AuditEvent {
  event_id: string
  '@timestamp': string
  actor: string
  action: string
  entity_type: string
  entity_id: string
  finding_key?: string | null
  decision_id?: string | null
  field?: string | null
  field_type?: string | null
  old_value?: string | null
  new_value?: string | null
  new_value_json?: Record<string, unknown> | null
  revision?: number | null
  cluster_id?: string
  /** read-time decoration (M9d): the finding this event touched, null once aged out */
  finding?: {
    cve_id: string
    image_repo?: string | null
    image_digest?: string | null
    scanner?: string | null
    package_name?: string | null
    severity_canonical?: string | null
  } | null
  /** read-time decoration: the decision this event touched */
  decision?: {
    cve_id: string
    type?: string | null
    scanner?: string | null
    apply_both_scanners?: boolean | null
  } | null
}

export const useAuditStore = defineStore('audit', () => {
  const pager = useCursorPager()
  const rows = ref<AuditEvent[]>([])
  const total = ref(0)
  const totalIsLowerBound = ref(false)
  const loading = ref(false)
  /** A read for the current query has come back at least once: before that the count is
   * unknown, not zero (issue 833, G3). */
  const settled = ref(false)
  const failed = ref(false)
  const failedStatus = ref<number | null>(null)
  /** The total belongs to the current filters: answered, or a refused later page of the same
   * query, whose total page 1 already gave (operator ruling 2026-10-13, issue 833). */
  const totalKnown = computed(() => settled.value && (!failed.value || pager.page.value > 0))

  function setResult(
    newRows: AuditEvent[],
    newTotal: { value: number; relation: string },
    nextCursor: string | null,
    live = false,
  ) {
    rows.value = newRows
    total.value = newTotal.value
    totalIsLowerBound.value = newTotal.relation !== 'eq'
    settled.value = true
    failed.value = false
    failedStatus.value = null
    pager.landed(nextCursor, live)
  }
  /** A read was refused: no rows are shown, since they answered another query or page. A refused
   * first page drops the total too; a refused later page keeps it, so the pager stays there. */
  function setFailed(status: number | null) {
    rows.value = []
    if (pager.page.value === 0) {
      total.value = 0
      totalIsLowerBound.value = false
    }
    failed.value = true
    failedStatus.value = status
    settled.value = true
  }
  /** Cluster or T switched — the held rows belong to another tenant/world; drop them so the
   * loading state shows instead of readable stale data while the new read is in flight. */
  function clearResults() {
    rows.value = []
    total.value = 0
    totalIsLowerBound.value = false
    settled.value = false
    pager.reset()
  }

  return {
    rows,
    total,
    totalIsLowerBound,
    size: pager.size,
    page: pager.page,
    loading,
    settled,
    failed,
    failedStatus,
    totalKnown,
    hasPrev: pager.hasPrev,
    hasNext: pager.hasNext,
    /** Cursor to fetch the CURRENT page with. */
    activeCursor: pager.cursor,
    setResult,
    setFailed,
    goNext: pager.next,
    goPrev: pager.prev,
    setSize: pager.setSize,
    /** Filters/globals changed or a cursor went stale — back to page 0, stack rebuilt. */
    resetPaging: pager.reset,
    clearResults,
  }
})

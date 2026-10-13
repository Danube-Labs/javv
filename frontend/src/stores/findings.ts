/**
 * Grid state for the findings table. The shipped M6 contract pages by cursor (PIT +
 * search_after) — there is no offset, so no random page jumps: the pager walks prev/next over a
 * cursor stack kept by `useCursorPager`. Everything displayed (rows, total) is the server's —
 * nothing is counted or paged client-side. A store, not component state, so the grid keeps its
 * page and sort when the user opens a finding and comes back. Leaving for any other screen closes
 * the walk and brings the grid back on page 1 (`FindingsView`, ruling on issue 832).
 *
 * Cursors embed a PIT that the server expires after a while — a stale-cursor fetch fails and the
 * caller resets to page 0 (`resetPaging`).
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { useCursorPager } from '@/composables/useCursorPager'
import type { SortField, SortOrder } from '@/findings/buildFindingsQuery'

/** The findings-search row shape this bolt renders (subset of the server doc; B-2: only real fields). */
export interface FindingRow {
  finding_key: string
  cve_id: string
  scanner: string
  severity: string
  severity_canonical: string
  image_repo: string
  tag: string | null
  package_name: string
  installed_version: string | null
  fixed_version: string | null
  fixable: boolean
  epss: number | null
  kev: boolean
  ptype: string | null
  state: string
  disagree?: boolean
  assignee?: string | null
  overdue: boolean
  due_at: string | null
  first_seen_at?: string | null
  last_scan_at?: string | null
  [key: string]: unknown
}

export const useFindingsStore = defineStore('findings', () => {
  const pager = useCursorPager()
  const rows = ref<FindingRow[]>([])
  const total = ref(0)
  const sort = ref<SortField>('severity_rank')
  const order = ref<SortOrder>('desc')
  const loading = ref(false)
  /** A read for the current (cluster, T, filters) has come back at least once. `loading` alone
   * cannot carry this: before the cluster resolves no request has started, so a grid gated on
   * `loading` spends that window claiming the cluster is empty. Unknown is not zero. */
  const settled = ref(false)
  const failed = ref(false)
  const failedStatus = ref<number | null>(null)
  /** The total belongs to the current filters: answered, or a refused later page of the same
   * query, whose total page 1 already gave (operator ruling 2026-10-13, issue 833). */
  const totalKnown = computed(() => settled.value && (!failed.value || pager.page.value > 0))

  /** `live`: a read at T=now, whose walk holds a search the pager closes when it drops it. */
  function setResult(
    newRows: FindingRow[],
    newTotal: number,
    nextCursor: string | null,
    live = false,
  ) {
    rows.value = newRows
    total.value = newTotal
    settled.value = true
    pager.landed(nextCursor, live)
  }
  /** A read was refused: no rows are shown, since they answered another query or page. A refused
   * first page drops the total too; a refused later page keeps it, because page 1 of the same
   * query answered it, so the pager can stay on that page. */
  function setFailed(status: number | null) {
    rows.value = []
    if (pager.page.value === 0) total.value = 0
    failed.value = true
    failedStatus.value = status
    settled.value = true
  }
  function setSort(field: SortField) {
    // same column toggles direction; a new column starts desc (prototype behavior)
    order.value = sort.value === field ? (order.value === 'desc' ? 'asc' : 'desc') : 'desc'
    sort.value = field
    pager.reset()
  }
  /** Cluster or T switched — the held rows belong to another tenant/world; drop them so the
   * loading state shows instead of readable stale data while the new read is in flight. */
  function clearResults() {
    rows.value = []
    total.value = 0
    settled.value = false
    pager.reset()
  }

  return {
    rows,
    total,
    sort,
    order,
    size: pager.size,
    page: pager.page,
    cursors: pager.cursors,
    nextCursor: pager.nextCursor,
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
    setSort,
    setSize: pager.setSize,
    /** Filters/sort/size changed or a cursor went stale — back to page 0, stack rebuilt. */
    resetPaging: pager.reset,
    clearResults,
  }
})

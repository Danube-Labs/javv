/**
 * The value search of the filter bar (issue 1064): when a field's list stopped at the top 32,
 * the typed text asks the server for the values that contain it. Debounced from 2 letters, the
 * same as the global search; a sequence stamp drops an older answer, and a result belongs to
 * the field and text it was asked for, so it never shows under another one.
 */
import { ref } from 'vue'

import { client } from '@/api/client'
import {
  approvalListApiV1DecisionsApprovalsGet,
  auditFacetsApiV1AuditFacetsGet,
  facetFindingsApiV1FindingsFacetsGet,
} from '@/api/generated'
import type { FacetBucket, ValueSearch, ValueSearchFn } from '@/filters/facets'
import type { FilterField } from '@/filters/fields.config'
import { logger } from '@/lib/logger'

const DEBOUNCE_MS = 250
export const MIN_CHARS = 2

export function useValueSearch() {
  /** the answer, with the field and text it answers */
  const answer = ref<{ field: string; text: string; result: ValueSearch } | null>(null)
  const failed = ref(false)

  let timer: ReturnType<typeof setTimeout> | undefined
  let seq = 0

  async function run(search: ValueSearchFn, field: FilterField, text: string) {
    const mine = ++seq
    const result = await search(field, text)
    if (mine !== seq) return // a newer keystroke owns the state now
    failed.value = result === null
    answer.value = result ? { field: field.key, text, result } : null
  }

  function ask(search: ValueSearchFn, field: FilterField, raw: string) {
    clearTimeout(timer)
    const text = raw.trim()
    if (text.length < MIN_CHARS) {
      reset()
      return
    }
    timer = setTimeout(() => void run(search, field, text), DEBOUNCE_MS)
  }

  function reset() {
    clearTimeout(timer)
    seq++ // orphan any answer in flight
    answer.value = null
    failed.value = false
  }

  /** The answer for this field and text, or null while it is not there. */
  function resultFor(field: string, raw: string): ValueSearch | null {
    const a = answer.value
    return a && a.field === field && a.text === raw.trim() ? a.result : null
  }

  return { failed, ask, reset, resultFor }
}

type ListQuery = () => Record<string, unknown> | null | undefined

/** The values of `key` in the answer of a value search, or null when the server refused it.
 * A bucket with no scanner split (Approvals) gets an empty one, the shape of the lists. */
function readAnswer(
  event: string,
  key: string,
  data: unknown,
  response: Response | undefined,
): ValueSearch | null {
  if (!response?.ok || !data) {
    logger.warn(event, { status: response?.status })
    return null
  }
  const out = data as { facets?: Record<string, Omit<FacetBucket, 'by_scanner'>[]>; more?: boolean }
  const buckets = (out.facets?.[key] ?? []).map((b) => ({ by_scanner: {}, ...b }))
  return { buckets, more: out.more === true }
}

/** A value search over the findings facets, with the filters of the list (`query`): the
 * Findings screen and the panel settings of a dashboard. */
export function findingsValueSearch(query: ListQuery): ValueSearchFn {
  return async (field, text) => {
    const q = query()
    const key = field.type === 'terms' ? field.facetKey : undefined
    if (!q || !key) return null
    const { data, response } = await facetFindingsApiV1FindingsFacetsGet({
      client,
      query: { ...q, fields: [key], contains: text } as never,
    })
    return readAnswer('findings_value_search_failed', key, data, response)
  }
}

/** A value search over the Audit log User list, with the filters of the list (`query`). The
 * server searches the `actor` values only. */
export function auditValueSearch(query: ListQuery): ValueSearchFn {
  return async (field, text) => {
    const q = query()
    if (!q || field.type !== 'terms' || field.facetKey !== 'actor') return null
    const { data, response } = await auditFacetsApiV1AuditFacetsGet({
      client,
      query: { ...q, contains: text } as never,
    })
    return readAnswer('audit_value_search_failed', 'actor', data, response)
  }
}

/** A value search over the Approvals Approver list, with the filters and the `warn_days` of
 * the list (`query`). The server searches the `created_by` values only. */
export function approvalsValueSearch(query: ListQuery): ValueSearchFn {
  return async (field, text) => {
    const q = query()
    if (!q || field.type !== 'terms' || field.facetKey !== 'created_by') return null
    const { data, response } = await approvalListApiV1DecisionsApprovalsGet({
      client,
      query: { ...q, contains: text } as never,
    })
    return readAnswer('approvals_value_search_failed', 'created_by', data, response)
  }
}

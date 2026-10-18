/**
 * The payload of a bulk-triage audit row: one row for the whole change, with the patch and the
 * frozen ids in `new_value_json`. The Audit table and a finding's Activity card both read it.
 */

export interface BulkJson {
  patch?: Record<string, unknown>
  target_ids?: string[]
  result_count?: number
}

/** The payload of a bulk-triage row, or null for any other row. */
export const bulkJson = (e: { action: string; new_value_json?: Record<string, unknown> | null }): BulkJson | null =>
  e.action === 'bulk_triage' && e.new_value_json ? (e.new_value_json as BulkJson) : null

/** What a bulk change set, field by field; null for a row that is not a bulk change. */
export function bulkChange(e: {
  action: string
  new_value_json?: Record<string, unknown> | null
}): { state: string | null; assignee: string | null; notes: string | null } | null {
  const bulk = bulkJson(e)
  if (!bulk) return null
  const text = (v: unknown) => (typeof v === 'string' && v ? v : null)
  return { state: text(bulk.patch?.state), assignee: text(bulk.patch?.assignee), notes: text(bulk.patch?.notes) }
}

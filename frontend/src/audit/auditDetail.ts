/**
 * The one-line text of an audit change: the Detail column of the Audit log and the detail line of
 * the Contributors feed. Fields and values read by their plain names (`fieldLabels.ts`).
 */
import { bulkJson } from '@/audit/bulkAudit'
import { fieldLabel, fieldValue } from '@/audit/fieldLabels'

interface Change {
  action: string
  field?: string | null
  old_value?: string | null
  new_value?: string | null
  new_value_json?: Record<string, unknown> | null
}

/** The Audit log's line; empty when the tag and the target already say it all (auth events). */
export function auditDetail(e: Change): string {
  const bulk = bulkJson(e)
  if (bulk) {
    const patch = Object.entries(bulk.patch ?? {})
      .map(([k, v]) => `${fieldLabel(k)} → ${fieldValue(k, String(v))}`)
      .join(' · ')
    return `${patch}: ${bulk.result_count ?? '?'} findings (frozen set)`
  }
  const field = e.field
  if (field == null) return ''
  if (e.old_value == null && e.new_value == null) return ''
  const label = fieldLabel(field)
  if (e.old_value == null) return `${label}: ${fieldValue(field, e.new_value!)}`
  if (e.new_value == null) return `${label}: ${fieldValue(field, e.old_value)} cleared`
  return `${label}: ${fieldValue(field, e.old_value)} → ${fieldValue(field, e.new_value)}`
}

/** The Contributors feed's line: the journaled field change, nothing invented. */
export function feedDetail(e: Change): string {
  const field = e.field
  if (!field) return ''
  const to = e.new_value != null ? fieldValue(field, e.new_value) : e.new_value_json ? 'updated' : '∅'
  return `${fieldLabel(field)} → ${to}`
}

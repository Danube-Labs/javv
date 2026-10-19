/**
 * The one-line text of an audit change: the Detail column of the Audit log and the detail line of
 * the Contributors feed. Fields and values read by their plain names (`fieldLabels.ts`).
 */
import { bulkJson } from '@/audit/bulkAudit'
import { fieldLabel, fieldValue, reasonLabel } from '@/audit/fieldLabels'
import { JSON_KEYS, jsonChange } from '@/audit/jsonChange'

interface Change {
  action: string
  field?: string | null
  old_value?: string | null
  new_value?: string | null
  old_value_json?: Record<string, unknown> | null
  new_value_json?: Record<string, unknown> | null
}

/**
 * A settings change or a job run keeps its values only as JSON (`jsonChange.ts`). Other JSON, a
 * bulk change for one, has its own line.
 */
const jsonOnly = (e: Change, field: string): string =>
  field in JSON_KEYS && e.old_value == null && e.new_value == null && e.new_value_json
    ? jsonChange(field, e.old_value_json, e.new_value_json)
    : ''

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
  if (e.old_value == null && e.new_value == null) return jsonOnly(e, field)
  const label = fieldLabel(field)
  if (e.old_value == null) return `${label}: ${fieldValue(field, e.new_value!)}${reasonPart(e)}`
  if (e.new_value == null) return `${label}: ${fieldValue(field, e.old_value)} cleared`
  return `${label}: ${fieldValue(field, e.old_value)} → ${fieldValue(field, e.new_value)}${reasonPart(e)}`
}

/** A change to Not affected keeps its reason beside the state, in `new_value_json`. */
function reasonPart(e: Change): string {
  const reason = e.field === 'state' ? e.new_value_json?.['vex_justification'] : undefined
  return typeof reason === 'string' ? ` · ${fieldLabel('vex_justification')}: ${reasonLabel(reason)}` : ''
}

/** The Contributors feed's line: the journaled field change, nothing invented. */
export function feedDetail(e: Change): string {
  const field = e.field
  if (!field) return ''
  const json = jsonOnly(e, field)
  if (json) return json
  const to = e.new_value != null ? fieldValue(field, e.new_value) : e.new_value_json ? 'updated' : '∅'
  return `${fieldLabel(field)} → ${to}`
}

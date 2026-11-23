/** Pure builders for the export dialog (audit F-07/F-08): the scheduled export carries the
 * COMPLETE visible lens — every ExportParams field the backend contract knows — and a lens
 * key the contract can't represent blocks scheduling loudly, never silently widening the
 * export. `export-params.spec.ts` compares this list with `ExportParams` in openapi.json, so
 * a field the backend gains fails that spec until it is added here (issue 962). */

import { FINDINGS_EXCLUSIVE_PAIRS, FINDINGS_FIELDS, type FilterField } from '@/filters/fields.config'

export const EXPORT_PARAM_KEYS = [
  'severity', 'state', 'scanner', 'assignee', 'kev', 'fixable', 'disagree', 'cve_id',
  'image_digest', 'image_repo', 'namespace', 'ptype', 'package_name', 'tag', 'q', 'present',
  'new_within_days', 'overdue', 'unassigned', 'untagged', 'exclude_severity', 'exclude_state',
  'exclude_scanner', 'exclude_assignee', 'exclude_image_repo', 'exclude_namespace',
  'exclude_ptype', 'exclude_cve_id', 'exclude_package_name', 'exclude_tag',
] as const

const GLOBAL_KEYS = new Set(['cluster_id', 'as_of', 'window_days'])

/** Lens keys the schedule contract cannot carry (globals excluded). Non-empty = block. */
export function unrepresentableKeys(lensQuery: Record<string, unknown>): string[] {
  return Object.keys(lensQuery).filter(
    (k) => !GLOBAL_KEYS.has(k) && !(EXPORT_PARAM_KEYS as readonly string[]).includes(k),
  )
}

/** What the screen calls each key: a field's label, also for its exclude side, or a flag's
 * label. A key that no field has keeps its own name. */
export function filterNames(fields: readonly FilterField[], keys: readonly string[]): string[] {
  const names = new Map<string, string>()
  for (const field of fields) {
    if (field.type === 'flags') {
      for (const flag of field.values) names.set(flag.param, flag.label)
    } else {
      names.set(field.param, field.label)
      names.set(`exclude_${field.param}`, field.label)
    }
  }
  return [...new Set(keys.map((key) => names.get(key) ?? key))]
}

/** The filters the backend cannot answer at a past time, because the scan history does not
 * record them (`_unrecorded` in backend/src/backend/query/as_of_t.py). `export-params.spec.ts`
 * keeps this list equal to the backend's. */
export const PAST_TIME_UNRECORDED_KEYS = ['kev', 'disagree', 'new_within_days'] as const

/** The query holds a filter that a past time refuses: the past-time text names these filters. */
export const hasUnrecordedFilter = (query: Record<string, unknown>): boolean =>
  PAST_TIME_UNRECORDED_KEYS.some((key) => query[key] !== undefined)

/** The query keys of a pair that the backend refuses with 422 (`FINDINGS_EXCLUSIVE_PAIRS` in
 * filters/fields.config.ts: Assignee with Unassigned, Tag with No tag), or null. A link can hold
 * one, since the store keeps both until the user picks one of the two. */
export function refusedPair(query: Record<string, unknown>): [string, string] | null {
  for (const pair of FINDINGS_EXCLUSIVE_PAIRS) {
    const field = FINDINGS_FIELDS.find((f) => f.key === pair.field)
    const flags = FINDINGS_FIELDS.find((f) => f.key === pair.flagField)
    const flag = flags?.type === 'flags' ? flags.values.find((v) => v.key === pair.flag) : undefined
    if (!field || field.type === 'flags' || !flag) continue
    if (query[field.param] !== undefined && query[flag.param] !== undefined) return [field.param, flag.param]
  }
  return null
}

/** What the user picked in the export dialog. */
export interface ExportChoice {
  /** The Schedule tab; false is Run now. */
  schedule: boolean
  /** A past time is picked: only a schedule can export it. */
  historical: boolean
  format: 'csv' | 'vex'
  vexScanner: string
}

/** Why this export cannot run, or null. Each case is a request that the backend refuses, or one
 * that would export other rows than the screen shows (issue 962). */
export function exportBlockMessage(
  fields: readonly FilterField[],
  query: Record<string, unknown>,
  choice: ExportChoice,
): string | null {
  if (choice.schedule) {
    const offenders = unrepresentableKeys(query)
    if (offenders.length)
      return `An export in the background cannot use these filters: ${filterNames(fields, offenders).join(', ')}. ${choice.historical ? 'Clear them.' : 'Clear them, or use Run now.'}`
    const unrecorded = choice.historical
      ? PAST_TIME_UNRECORDED_KEYS.filter((key) => query[key] !== undefined)
      : []
    if (unrecorded.length)
      return `At a past time, an export in the background cannot use these filters: ${filterNames(fields, unrecorded).join(', ')}. Clear them.`
  }
  const pair = refusedPair(query)
  if (pair) return `An export cannot use ${filterNames(fields, pair).join(' and ')} together. Clear one of them.`
  if (choice.format === 'vex') {
    if (query.exclude_scanner !== undefined)
      return 'A VEX file covers one scanner. Clear the Scanner filter first.'
    if (query.scanner !== undefined && query.scanner !== choice.vexScanner)
      return `This screen shows ${String(query.scanner)} findings only. Select ${String(query.scanner)} for the VEX file.`
  }
  return null
}

/** The ExportParams blob for one schedule: whole lens + format; VEX pins its one scanner. */
export function scheduleParams(
  lensQuery: Record<string, unknown>,
  format: 'csv' | 'vex',
  vexScanner: string,
): Record<string, unknown> {
  const params: Record<string, unknown> = {
    format: format === 'csv' ? 'csv' : 'openvex',
  }
  for (const key of EXPORT_PARAM_KEYS) {
    if (lensQuery[key] !== undefined) params[key] = lensQuery[key]
  }
  if (format === 'vex') params.scanner = vexScanner // one scanner per VEX file (sacred)
  return params
}

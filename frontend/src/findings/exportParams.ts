/** Pure builders for the export dialog (audit F-07/F-08): the scheduled export carries the
 * COMPLETE visible lens — every ExportParams field the backend contract knows — and a lens
 * key the contract can't represent blocks scheduling loudly, never silently widening the
 * export. `export-params.spec.ts` compares this list with `ExportParams` in openapi.json, so
 * a field the backend gains fails that spec until it is added here (issue 962). */

import type { FilterField } from '@/filters/fields.config'

export const EXPORT_PARAM_KEYS = [
  'severity', 'state', 'scanner', 'assignee', 'kev', 'fixable', 'disagree', 'cve_id',
  'image_digest', 'image_repo', 'namespace', 'ptype', 'package_name', 'q', 'present',
  'new_within_days', 'overdue', 'unassigned', 'exclude_severity', 'exclude_state',
  'exclude_scanner', 'exclude_assignee', 'exclude_image_repo', 'exclude_namespace',
  'exclude_ptype', 'exclude_cve_id', 'exclude_package_name',
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

/** Why this lens cannot be scheduled, or null. Assignee with Unassigned is refused by Findings
 * and by the schedule route alike, so the dialog says so instead of a failed request. */
export function scheduleBlockMessage(
  fields: readonly FilterField[],
  lensQuery: Record<string, unknown>,
): string | null {
  const offenders = unrepresentableKeys(lensQuery)
  if (offenders.length)
    return `A schedule cannot use these filters: ${filterNames(fields, offenders).join(', ')}. Clear them, or use Run now.`
  if (lensQuery.assignee !== undefined && lensQuery.unassigned !== undefined)
    return `A schedule cannot use ${filterNames(fields, ['assignee', 'unassigned']).join(' and ')} together. Clear one of them.`
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

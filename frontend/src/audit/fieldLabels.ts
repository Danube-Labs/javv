/**
 * What a journaled field is CALLED on screen, and how its value reads (issue 931). Read by the
 * Audit log's Detail column, the Contributors feed and a finding's Activity card. The names are
 * the ones of the screen that sets the value: the triage panel, the settings pages. The stored
 * field and value do not change; the CSV export and the API keep them.
 */
import { stateLabel } from '@/findings/stateLabels'
import { CISA_JUSTIFICATIONS } from '@/findings/triageRules'

export const FIELD_LABELS: Record<string, string> = {
  state: 'State',
  vex_justification: 'Reason',
  assignee: 'Assigned to',
  notes: 'Note',
  bulk_patch: 'Bulk change',
  lifecycle: 'Decision',
  view: 'Saved view',
  dashboard: 'Dashboard',
  sla_policy: 'SLA policy',
  scan_scope: 'Scan scope',
  staleness_timers: 'Staleness timers',
  cluster_name: 'Cluster name',
  retired: 'Retired',
  retirement_window: 'Cluster retirement',
  deleted: 'Cluster',
  leftovers: 'Leftover rows',
  retention_days: 'History retention',
  cleanup_days: 'Findings cleanup window',
  hours: 'Report/export retention',
  rollover: 'Rollover thresholds',
  snapshot: 'Snapshot',
  counts: 'Counts',
}

/** The display name of a field; one with no entry reads as its words, never as snake_case. */
export const fieldLabel = (field: string): string => FIELD_LABELS[field] ?? field.replace(/_/g, ' ')

/** The plain label of a Not affected reason; one not in the list shows as it is. */
export const reasonLabel = (id: string): string => CISA_JUSTIFICATIONS.find((j) => j.id === id)?.label ?? id

/**
 * The number settings the backend keeps as floats: a saved 105 is written as "105.0", while the
 * default it replaced is "90". Only these fields lose the ".0", since a cluster name can look
 * like a number.
 */
const NUMBER_FIELDS = new Set(['retention_days', 'cleanup_days', 'hours'])

/** A value as it reads: a state or a reason by its label, any other value as it is. */
export function fieldValue(field: string, value: string): string {
  if (field === 'state') return stateLabel(value)
  if (field === 'vex_justification') return reasonLabel(value)
  if (NUMBER_FIELDS.has(field)) return value.replace(/^(-?\d+)\.0+$/, '$1')
  return value
}

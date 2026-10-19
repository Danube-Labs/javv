/**
 * The text of an audit row that keeps its values only as JSON: a settings change (the backend
 * writes the whole setting before and after) or a job run (its counts). The names and units are
 * the ones of the screen that sets the value. A row with old values shows only the keys that
 * changed; a row with none, a job run, shows all its keys.
 */
import { fieldLabel } from '@/audit/fieldLabels'

interface KeyName {
  label: string
  unit?: string
  /** how an empty value reads; a retirement window of null means the cluster never retires */
  empty?: string
}

export const JSON_KEYS: Record<string, Record<string, KeyName>> = {
  sla_policy: {
    critical_days: { label: 'Critical', unit: 'days' },
    high_days: { label: 'High', unit: 'days' },
    medium_days: { label: 'Medium', unit: 'days' },
    low_days: { label: 'Low', unit: 'days' },
    kev_days: { label: 'KEV override', unit: 'days' },
  },
  staleness_timers: {
    freshness_days: { label: 'Per-finding freshness', unit: 'days' },
    scanner_down_days: { label: 'Scanner-down escalation', unit: 'days' },
  },
  scan_scope: {
    include_namespaces: { label: 'Included namespaces' },
    ignore_namespaces: { label: 'Ignored namespaces' },
    exclude_images: { label: 'Excluded image patterns' },
    ignore_kinds: { label: 'Skip workload kinds' },
  },
  retirement_window: {
    retire_after_days: { label: 'Retire a silent cluster', unit: 'days', empty: 'Never' },
    warn_days: { label: 'Warn before', unit: 'days' },
  },
  rollover: {
    max_age_days: { label: 'Max age', unit: 'days' },
    max_docs: { label: 'Max docs', unit: 'docs' },
    max_size_gb: { label: 'Max primary size', unit: 'GB' },
    retention_days: { label: 'History retention', unit: 'days' },
  },
  counts: {
    findings_deleted: { label: 'Findings deleted' },
    watermarks_pruned: { label: 'Watermarks pruned' },
    cleanup_days: { label: 'Cleanup window', unit: 'days' },
    sessions_deleted: { label: 'Sessions deleted' },
    grace_hours: { label: 'Grace period', unit: 'hours' },
  },
}

/** Keys a row keeps for the record that do not fit on one line: the per-cluster counts. */
export const NOT_SHOWN = new Set(['by_cluster'])

type Json = Record<string, unknown>

const nameOf = (field: string, key: string): KeyName =>
  JSON_KEYS[field]?.[key] ?? { label: key.replace(/_/g, ' ') }

function text(v: unknown, name: KeyName): string {
  if (v === null || v === undefined) return name.empty ?? 'none'
  if (Array.isArray(v)) return v.length ? v.join(', ') : 'none'
  return String(v)
}

/** A value with its unit: "7 days", "Never", "kube-system, monitoring". */
function withUnit(v: unknown, name: KeyName): string {
  return typeof v === 'number' && name.unit ? `${v} ${name.unit}` : text(v, name)
}

/** "Critical 2 → 7 days": the unit once, at the end, when both sides are numbers. */
function changed(key: string, from: unknown, to: unknown, field: string): string {
  const name = nameOf(field, key)
  if (typeof from === 'number' && typeof to === 'number' && name.unit) {
    return `${name.label} ${from} → ${to} ${name.unit}`
  }
  return `${name.label} ${withUnit(from, name)} → ${withUnit(to, name)}`
}

const shown = (key: string, v: unknown): boolean =>
  !NOT_SHOWN.has(key) && !(typeof v === 'object' && v !== null && !Array.isArray(v))

/**
 * The line of a JSON-only row, for example "SLA policy: Critical 2 → 7 days". Empty when the row
 * has nothing to show.
 */
export function jsonChange(field: string, before: Json | null | undefined, after: Json): string {
  const keys = [...new Set([...Object.keys(after), ...Object.keys(before ?? {})])].filter((k) =>
    shown(k, after[k] ?? before?.[k]),
  )
  let parts: string[]
  if (before) {
    parts = keys
      .filter((k) => JSON.stringify(before[k]) !== JSON.stringify(after[k]))
      .map((k) => changed(k, before[k], after[k], field))
    if (keys.length && !parts.length) parts = ['no change']
  } else {
    parts = keys.map((k) => `${nameOf(field, k).label} ${withUnit(after[k], nameOf(field, k))}`)
  }
  return parts.length ? `${fieldLabel(field)}: ${parts.join(' · ')}` : ''
}

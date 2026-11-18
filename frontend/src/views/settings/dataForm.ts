/**
 * Pure form logic for the Data & OpenSearch panel (FR-19/D26 + rows 10/11/23) — parsing,
 * dirty/invalid derivation and the row-23 index-family registry, unit-tested; the view stays
 * a thin binding. All four setting groups share one SaveBar: save PUTs only the changed groups.
 */
import { parseWindow } from './slaForm'

/** Every setting the panel edits, as saved on the server (the GET /settings/data flattening). */
export interface DataSettings {
  retention_days: number
  max_age_days: number
  max_docs: number
  max_size_gb: number
  cleanup_days: number
  report_ttl_hours: number
}

/** The raw input halves — strings until save so partial typing never explodes. */
export interface DataDraft {
  retention: string
  maxAge: string
  maxDocs: string
  maxSize: string
  cleanup: string
  ttl: string
}

/** Positive integer or null — counts (max docs, TTL hours) reject decimals and junk. */
export function parseCount(raw: string): number | null {
  const trimmed = raw.trim()
  if (!/^\d+$/.test(trimmed)) return null
  const n = Number(trimmed)
  return Number.isSafeInteger(n) && n > 0 ? n : null
}

export function draftFromSettings(k: DataSettings): DataDraft {
  return {
    retention: String(k.retention_days),
    maxAge: String(k.max_age_days),
    maxDocs: String(k.max_docs),
    maxSize: String(k.max_size_gb),
    cleanup: String(k.cleanup_days),
    ttl: String(k.report_ttl_hours),
  }
}

/** Per-field parse results — null marks the invalid input (drives the field's invalid state). */
export function parseDraft(d: DataDraft): { [K in keyof DataSettings]: number | null } {
  return {
    retention_days: parseWindow(d.retention),
    max_age_days: parseWindow(d.maxAge),
    max_docs: parseCount(d.maxDocs),
    max_size_gb: parseWindow(d.maxSize),
    cleanup_days: parseWindow(d.cleanup),
    report_ttl_hours: parseCount(d.ttl),
  }
}

export function draftInvalid(d: DataDraft): boolean {
  return Object.values(parseDraft(d)).some((v) => v === null)
}

/** Semantic dirty: a re-typed identical value ("30" → "30.0") is NOT a change. */
export function draftDirty(saved: DataSettings, d: DataDraft): boolean {
  const parsed = parseDraft(d)
  return (Object.keys(parsed) as (keyof DataSettings)[]).some(
    (k) => parsed[k] !== null && parsed[k] !== saved[k],
  )
}

/** Which PUTs a save must issue (retention / rollover / cleanup / ttl), given what changed. */
export function changedGroups(
  saved: DataSettings,
  d: DataDraft,
): { retention: boolean; rollover: boolean; cleanup: boolean; ttl: boolean } {
  const p = parseDraft(d)
  const differs = (k: keyof DataSettings) => p[k] !== null && p[k] !== saved[k]
  return {
    retention: differs('retention_days'),
    rollover: differs('max_age_days') || differs('max_docs') || differs('max_size_gb'),
    cleanup: differs('cleanup_days'),
    ttl: differs('report_ttl_hours'),
  }
}

/** The row-23 registry: EVERY index family, with why the protected ones take no retention. */
export interface FamilyRow {
  pattern: string
  purpose: string
  kind: 'append' | 'protected'
  why?: string
}

export const FAMILY_ROWS: FamilyRow[] = [
  {
    pattern: 'javv-finding-occurrences-*',
    purpose: 'the findings of each scan: the history. It sets how far back a past time can go.',
    kind: 'append',
  },
  {
    pattern: 'javv-scan-events-*',
    purpose: 'the list of complete scans and the trend charts',
    kind: 'append',
  },
  {
    pattern: 'javv-images-*',
    purpose: 'the history of the running images',
    kind: 'append',
  },
  {
    pattern: 'javv-inventory-runs-*',
    purpose: 'the record of each complete inventory',
    kind: 'append',
  },
  {
    pattern: 'javv-ingest-failures-*',
    purpose: 'the scans that the backend refused after it checked their token',
    kind: 'append',
  },
  {
    pattern: 'system-audit-log-*',
    purpose: 'who did what, and when',
    kind: 'protected',
    why: 'It rolls over on the thresholds for all clusters, but JAVV never deletes it. The audit history has no expiry.',
  },
  {
    pattern: 'findings',
    purpose: 'the current findings',
    kind: 'protected',
    why: 'JAVV can build it again, so it is not history. Only the findings cleanup window below cleans it, never the retention.',
  },
  {
    pattern: 'javv-scan-watermarks',
    purpose: 'the newest complete scan of each digest',
    kind: 'protected',
    why: 'It holds one row for each digest in the clusters now. The findings cleanup also deletes its old rows.',
  },
  {
    pattern: 'javv-scan-orders',
    purpose: 'the scan counter of each scanner',
    kind: 'protected',
    why:
      'The counter gives each scan its order. If you delete it, a new scan can get the number of a scan that is still in progress. Then JAVV cannot tell which scan is newer.',
  },
  {
    pattern: 'system-*',
    purpose: 'config · users · tokens · decisions · views · reports',
    kind: 'protected',
    why: 'Small data that changes. The snapshots hold it, but not the sessions, because a restored copy can make an ended session work again. It never expires. A separate sweep deletes old reports.',
  },
]

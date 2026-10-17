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
    purpose: 'per-scan CVE snapshots: the history, which bounds how far back time-travel reaches',
    kind: 'append',
  },
  {
    pattern: 'javv-scan-events-*',
    purpose: 'commit catalog + trend charts',
    kind: 'append',
  },
  {
    pattern: 'javv-images-*',
    purpose: 'inventory snapshots: running-images history',
    kind: 'append',
  },
  {
    pattern: 'javv-inventory-runs-*',
    purpose: 'inventory commit manifests',
    kind: 'append',
  },
  {
    pattern: 'javv-ingest-failures-*',
    purpose: 'pushes the backend refused after checking their token',
    kind: 'append',
  },
  {
    pattern: 'system-audit-log-*',
    purpose: 'who-did-what journal',
    kind: 'protected',
    why: 'rolls on the fleet thresholds but is NEVER dropped: audit history has no expiry in MVP',
  },
  {
    pattern: 'findings',
    purpose: 'the mutable "now" cache',
    kind: 'protected',
    why: 'rebuildable cache, not history: cleaned only by the long cleanup window below, never a retention drop',
  },
  {
    pattern: 'javv-scan-watermarks',
    purpose: 'per-digest commit watermarks',
    kind: 'protected',
    why: 'bounded by the live fleet; its rows prune together with the findings cleanup',
  },
  {
    pattern: 'javv-scan-orders',
    purpose: 'per-scanner order counters',
    kind: 'protected',
    why:
      'the counter that orders every scan. Deleting it could give a new scan the number already handed to one still in flight, and JAVV could no longer tell which is newer',
  },
  {
    pattern: 'system-*',
    purpose: 'config · users · tokens · decisions · views · reports',
    kind: 'protected',
    why: 'small mutable state: snapshotted for durability except the sessions (a restored copy could revive an ended one), never expired (reports TTL-swept separately)',
  },
]

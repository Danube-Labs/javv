/**
 * The global app state ⇄ URL (restorable-state rule, audit 343; issue 433): `t` (the D28 rewind
 * point, ISO), `win` (trend-window days, fractional allowed) and `cluster` (the selected
 * cluster_id — per-browser defaults differ, so a shared link must carry the tenant explicitly)
 * ride every screen's query like filters do — a pasted link reproduces exactly what the sender
 * saw, and a reload keeps the context. T=now + the 30-day default serialize to NOTHING, so
 * everyday URLs stay clean; the cluster always serializes once selected. Pure + unit-tested;
 * the AppShell owns the setup. (Formerly timeTravelUrl.ts — grew the cluster key.)
 */
import type { LocationQuery, LocationQueryRaw } from 'vue-router'

const DEFAULT_WIN = 30

export function ttToQuery(t: string | null, windowDays: number): Record<string, string> {
  const q: Record<string, string> = {}
  if (t !== null) q.t = t
  // 4 decimals ≈ 9-second resolution — plenty for a trend window, keeps URLs readable
  if (windowDays !== DEFAULT_WIN) q.win = String(Math.round(windowDays * 10000) / 10000)
  return q
}

/** null = the URL carries no range at all (leave the store's defaults untouched). Garbage
 * values degrade to the defaults rather than poisoning every read. */
export function ttFromQuery(query: LocationQuery): { t: string | null; win: number } | null {
  const rawT = typeof query.t === 'string' ? query.t : null
  const rawW = typeof query.win === 'string' ? query.win : null
  if (rawT === null && rawW === null) return null
  const t = rawT !== null && Number.isFinite(Date.parse(rawT)) ? new Date(rawT).toISOString() : null
  const n = rawW !== null ? Number(rawW) : NaN
  const win = Number.isFinite(n) && n > 0 ? Math.min(365, n) : DEFAULT_WIN
  return { t, win }
}

/** The label of a range that a URL restores at now (`win` in days). A whole number of days reads
 * in days. A length under 2 days reads in hours, or in minutes under 1 hour: an Exact range that
 * ends now has the length from its From time, which is rarely whole days (issue 1313). A longer
 * length reads in days with one decimal. */
export function nowWindowLabel(win: number): string {
  const last = (n: number, unit: string) => `Last ${n} ${unit}${n === 1 ? '' : 's'}`
  const hours = win * 24
  if (hours < 1) return last(Math.max(1, Math.round(hours * 60)), 'minute')
  if (hours < 48 && !Number.isInteger(win)) return last(Math.round(hours), 'hour')
  return last(Math.round(win * 10) / 10, 'day')
}

/** The `cluster` key of a deep link, shape-checked only — whether the id EXISTS is the cluster
 * store's call (it owns the registry and the unknown-id fallback). */
export function clusterFromQuery(query: LocationQuery): string | null {
  const raw = typeof query.cluster === 'string' ? query.cluster.trim() : ''
  return raw !== '' ? raw : null
}

/** The filter-sync rewrite base: everything the screen does NOT own. A screen's `router.replace`
 * may only overwrite its own vocabulary — the globals AND any foreign key (a specimen switch,
 * a future param) ride through untouched. The old global-key allowlist silently erased unknown
 * keys on every filter change. */
export function foreignQuery(query: LocationQuery, ownKeys: readonly string[]): LocationQuery {
  const out = { ...query }
  for (const k of ownKeys) delete out[k]
  return out
}

/** The screen's own subset in ownKeys order, blanks skipped — directly comparable against the
 * filter store's `toQuery()` output (which iterates the same fields config). */
export function ownQuery(query: LocationQuery, ownKeys: readonly string[]): Record<string, string> {
  const out: Record<string, string> = {}
  for (const k of ownKeys) {
    const v = query[k]
    if (typeof v === 'string' && v !== '') out[k] = v
  }
  return out
}

/** The shell's re-stamp target: the route's own query with the global keys set, and its hash
 * kept, so an in-page `#section` deep link (the Guide's anchors) survives the replace. */
export function restampLocation(
  query: LocationQuery,
  hash: string,
  tt: Record<string, string>,
  cluster: string | undefined,
): { query: LocationQueryRaw; hash: string } {
  return { query: { ...query, t: tt.t, win: tt.win, cluster }, hash }
}

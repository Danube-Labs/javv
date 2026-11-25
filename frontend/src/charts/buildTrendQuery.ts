/** Pure query-builders for the trends endpoints (M9c). A range of 2 days or less at now is exact:
 * the browser sends its length (`window_seconds`) and the backend counts back from its own clock
 * (issue 1291, rulings 1 and 2). A longer range, or a past T, is in whole days (`days` 1–365,
 * day-floored UTC bounds server-side): a sub-day span at a past T rounds UP to 1 day, and the
 * caller renders the daily-resolution caption. `as_of` rides in only at T<now (D28 — omit
 * entirely at now). */

export interface TrendQuery {
  cluster_id: string
  days?: number
  window_seconds?: number
  as_of?: string
}

/** the limits of `window_seconds` (`query/trends.EXACT_MIN_SECONDS`, `EXACT_MAX_SECONDS`) */
const EXACT_MIN_SECONDS = 60
const EXACT_MAX_SECONDS = 2 * 86_400

/** The exact length of the range in seconds, or null when the range is in whole days. Rounded to
 * the minute: the URL keeps the range with 4 decimals of a day, and `win=0.0417` is 1 hour and 3
 * seconds. */
export function exactWindowSeconds(windowDays: number, t: string | null): number | null {
  if (t !== null || windowDays > 2) return null
  const seconds = Math.round((windowDays * 86_400) / 60) * 60
  return Math.min(EXACT_MAX_SECONDS, Math.max(EXACT_MIN_SECONDS, seconds))
}

/** The whole days of a range: the API's 1–365. */
export function trendDays(windowDays: number): number {
  return Math.min(365, Math.max(1, Math.ceil(windowDays)))
}

/** The range of a read that takes `window_seconds` (`/trends/scans`, `/trends/ingest-failures`,
 * `/trends/new-findings`, `/scanners/ingest-failures`). */
export function buildTrendQuery(clusterId: string, windowDays: number, t: string | null): TrendQuery {
  const seconds = exactWindowSeconds(windowDays, t)
  const range = seconds === null ? { days: trendDays(windowDays) } : { window_seconds: seconds }
  return { cluster_id: clusterId, ...range, ...(t === null ? {} : { as_of: t }) }
}

/** The range of `/trends/findings`, which is daily only: always whole days. */
export function buildDailyTrendQuery(clusterId: string, windowDays: number, t: string | null): TrendQuery {
  return { cluster_id: clusterId, days: trendDays(windowDays), ...(t === null ? {} : { as_of: t }) }
}

/** True when the picker's chosen span is finer than the chart's 1-day floor. */
export function isSubDayWindow(windowDays: number): boolean {
  return windowDays > 0 && windowDays < 1
}

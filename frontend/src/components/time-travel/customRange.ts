/**
 * The range of an Exact range of the time picker (issue 1313). A range that ends now starts at its
 * From time, and the query builders make a length of 2 days or less exact and round a longer one up
 * to whole days, as for Quick select. A range that ends in the past keeps whole days, rounded to the
 * nearest day (ruling 5 of issue 1291).
 *
 * The user reads the To time on a clock, which can be the browser's or the backend's. A To time at
 * most a minute before now on either clock ends the range now, and its length is To less From, on
 * whole minutes as the fields: a range typed in whole days stays whole. A To time later than now on
 * both clocks ends the range now too, and its length runs to the minute of now on the clock of the
 * backend, which decides where a range starts (ruling 2 of issue 1291).
 */

const MIN_MS = 60_000
const DAY_MS = 86_400_000
/** a To time this close to now reads as now: the field has minutes only */
const NOW_SLACK_MS = 60_000
/** the shortest exact range of the API (`query/trends.EXACT_MIN_SECONDS`, 60 s) */
const MIN_DAYS = MIN_MS / DAY_MS
/** the longest range of the API (`days` 1..365) */
const MAX_DAYS = 365

export interface CustomRange {
  /** the length of the range in days, a fraction when it ends now */
  days: number
  /** true when the range ends now: the screens show the state of now, with no past time */
  endsNow: boolean
}

export function customRange(fromMs: number, toMs: number, serverMs: number, browserMs: number = serverMs): CustomRange {
  if (toMs < Math.min(serverMs, browserMs) - NOW_SLACK_MS) {
    return { days: Math.min(MAX_DAYS, Math.max(1, Math.round((toMs - fromMs) / DAY_MS))), endsNow: false }
  }
  const laterThanNow = toMs > Math.max(serverMs, browserMs) + NOW_SLACK_MS
  const endMs = laterThanNow ? Math.floor(serverMs / MIN_MS) * MIN_MS : toMs
  return { days: Math.min(MAX_DAYS, Math.max(MIN_DAYS, (endMs - fromMs) / DAY_MS)), endsNow: true }
}

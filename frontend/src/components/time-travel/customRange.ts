/**
 * The range of an Exact range of the time picker (issue 1313). A To time that is at most a minute
 * before now, or later, ends the range now: the range then starts at the From time, so its length
 * is now less From. The query builders make a length of 2 days or less exact and round a longer one
 * up to whole days, as for Quick select. A range that ends in the past keeps whole days, rounded to
 * the nearest day (ruling 5 of issue 1291). `nowMs` is the clock of the backend (`serverNow()`),
 * which decides where a range starts (ruling 2 of issue 1291).
 */

const DAY_MS = 86_400_000
/** a To time this close to now reads as now: the field has minutes only */
const NOW_SLACK_MS = 60_000
/** the shortest exact range of the API (`query/trends.EXACT_MIN_SECONDS`, 60 s) */
const MIN_DAYS = 60_000 / DAY_MS
/** the longest range of the API (`days` 1..365) */
const MAX_DAYS = 365

export interface CustomRange {
  /** the length of the range in days, a fraction when it ends now */
  days: number
  /** true when the range ends now: the screens show the state of now, with no past time */
  endsNow: boolean
}

export function customRange(fromMs: number, toMs: number, nowMs: number): CustomRange {
  if (toMs >= nowMs - NOW_SLACK_MS) {
    // a From later than now leaves no length: the range is the shortest one of the API
    return { days: Math.min(MAX_DAYS, Math.max(MIN_DAYS, (nowMs - fromMs) / DAY_MS)), endsNow: true }
  }
  return { days: Math.min(MAX_DAYS, Math.max(1, Math.round((toMs - fromMs) / DAY_MS) || 1)), endsNow: false }
}

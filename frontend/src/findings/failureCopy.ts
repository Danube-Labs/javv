/** Accurate-error rule (audit 343): every status the grid can receive maps to copy that names the
 * actual cause — a user-input 422 or a busy 429 must never read as a backend outage. */

export type FailureKind = 'past_t' | 'bad_filter' | 'busy' | 'expired' | 'backend'

/** `refusedPair`: the refused query held a pair the route refuses, Assignee with Unassigned or
 * Tag with No tag. The route refuses it before the past-time reader runs, so its 422 is never
 * about the past time (issues 975 and 1294). `unrecorded`: the query held a filter that a past
 * time refuses (`hasUnrecordedFilter`). The past-time text names those filters, so a 422 at a
 * past time without one gets the refused-filters text (issue 1294). */
export function failureKind(
  status: number | null,
  rewound: boolean,
  refusedPair = false,
  unrecorded = true,
): FailureKind {
  if (status === 501) return 'past_t'
  if (status === 422) return rewound && !refusedPair && unrecorded ? 'past_t' : 'bad_filter'
  if (status === 429) return 'busy'
  if (status === 410) return 'expired'
  return 'backend'
}

export const FAILURE_COPY: Record<FailureKind, string> = {
  // the scan history records the search fields, the image and the tag (issue 1294), so the text
  // names only PAST_TIME_UNRECORDED_KEYS (findings/exportParams.ts)
  past_t:
    'JAVV cannot apply the KEV, Scanners disagree or New in range filter at a past time. Go back to now, or remove these filters.',
  // a 1-character search never gets to the server (the search box stops it), so the text names
  // the causes that do
  bad_filter: 'JAVV refused the filters. Two of the filters cannot go together, or a value is not valid. Check the filters.',
  busy: 'The backend is busy. Try again in a few seconds.',
  // the cursor's search context is gone, so the page cannot be asked for again
  expired: 'These results expired. Reload the page to start again.',
  backend: 'JAVV cannot show the findings. Check the backend connection.',
}

/** Every read's alert (issue 833, G2): a 429 is the per-user search budget, never a broken
 * connection, so it gets the busy copy; a 410 is a later page whose search expired; any other
 * failure keeps the screen's own copy. */
export function readFailureCopy(status: number | null, fallback: string): string {
  if (status === 429) return FAILURE_COPY.busy
  if (status === 410) return FAILURE_COPY.expired
  return fallback
}

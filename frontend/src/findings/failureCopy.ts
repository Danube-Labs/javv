/** Accurate-error rule (audit 343): every status the grid can receive maps to copy that names the
 * actual cause — a user-input 422 or a busy 429 must never read as a backend outage. */

export type FailureKind = 'past_t' | 'bad_filter' | 'busy' | 'expired' | 'backend'

export function failureKind(status: number | null, rewound: boolean): FailureKind {
  if (status === 501) return 'past_t'
  if (status === 422) return rewound ? 'past_t' : 'bad_filter'
  if (status === 429) return 'busy'
  if (status === 410) return 'expired'
  return 'backend'
}

export const FAILURE_COPY: Record<FailureKind, string> = {
  past_t:
    "This filter isn't answerable at a past point in time. Return to now, or drop the search/attribute filters.",
  bad_filter: "This search or filter isn't valid: searches need at least 2 characters.",
  busy: 'The search backend is busy. Try again in a few seconds.',
  // the cursor's search context is gone, so the page cannot be asked for again
  expired: 'These results expired. Reload the page to start again.',
  backend: 'Findings unavailable. Check the backend connection.',
}

/** Every read's alert (issue 833, G2): a 429 is the per-user search budget, never a broken
 * connection, so it gets the busy copy; a 410 is a later page whose search expired; any other
 * failure keeps the screen's own copy. */
export function readFailureCopy(status: number | null, fallback: string): string {
  if (status === 429) return FAILURE_COPY.busy
  if (status === 410) return FAILURE_COPY.expired
  return fallback
}

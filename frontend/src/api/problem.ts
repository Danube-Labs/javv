/** The title of the backend's request-validation 422 (`core/errors.py`, pinned by
 * `problem.spec.ts`). */
export const VALIDATION_TITLE = 'Validation error'

/** The problem `type` of a write the store refused because its disk is full (`core/errors.py`,
 * pinned by `problem.spec.ts`). */
export const STORE_READ_ONLY_TYPE = 'store-read-only'

/** The problem `type` of the 409 for a cluster whose delete stopped halfway (`core/errors.py`,
 * pinned by `problem.spec.ts`). Matched instead of the title, which may be reworded. */
export const DELETE_UNFINISHED_TYPE = 'cluster-delete-unfinished'

/** Server messages (409 last-admin, 422 policy) surface VERBATIM — the backend speaks RFC-7807
 * and an HTTPException's text lands in the problem's `title`. Pydantic validation 422s only say
 * "Validation error" (their detail is a repr, not user copy) — those get the caller's fallback.
 * The hey-api client already consumed the body: read the parsed `error`, never `response`. */
export function detailOr(error: unknown, fallback: string): string {
  const title = (error as { title?: unknown } | undefined)?.title
  return typeof title === 'string' && title !== VALIDATION_TITLE ? title : fallback
}

/**
 * Closing the cursor walks the UI stops using (issue 832). A live findings or audit walk holds one
 * of the user's search slots on the server until its last page or its keep-alive; a list the user
 * leaves, a filter that starts a new walk, or a first page a newer read replaced would otherwise
 * hold it for minutes, and enough of them refuse the next list with 429.
 *
 * Only a live walk's cursor is closed here: a past-T findings cursor holds no search, and the
 * backend refuses it as a cursor to close. Best effort: a failed close changes nothing the user
 * sees, because the slot expires by itself. The walks still held when the page goes (a reload, a
 * closed tab) are closed on `pagehide` with `keepalive` requests, which outlive the page.
 */
import { closeCursorApiV1CursorsClosePost } from '@/api/generated'
import { logger } from '@/lib/logger'

const held = new Set<string>()
let listening = false

/** Close a walk now. Its cursor is no longer held, whatever the answer. */
export function closeCursor(cursor: string, keepalive = false): void {
  held.delete(cursor)
  void closeCursorApiV1CursorsClosePost({ body: { cursor }, keepalive }).then(({ response }) => {
    if (!response?.ok) logger.debug('cursor_close_failed', { status: response?.status ?? null })
  })
}

/** A walk the UI keeps open: closed on `pagehide` unless it is released or closed first. */
export function holdCursor(cursor: string): void {
  held.add(cursor)
  if (!listening) {
    listening = true
    window.addEventListener('pagehide', () => {
      for (const cursor of held) closeCursor(cursor, true) // deleting the current entry is safe
    })
  }
}

/** The walk ended or moved on to a newer cursor of the same search: nothing to close for it. */
export function releaseCursor(cursor: string): void {
  held.delete(cursor)
}

/** A first page whose walk nobody will page: a one-shot read, or an answer a newer read replaced.
 * `live` as in `useCursorPager.landed`; its search is closed at once. */
export function closeUnpaged(nextCursor: unknown, live: boolean): void {
  if (live && typeof nextCursor === 'string' && nextCursor) closeCursor(nextCursor)
}

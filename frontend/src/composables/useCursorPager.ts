/**
 * Cursor-stack paging for a server-paged table: the backend hands back an opaque
 * `next_cursor` per page, so going BACK means remembering the cursor that fetched each page
 * already seen. `cursors[i]` is the cursor that FETCHES page i; page 0's is always `null`.
 *
 * Owns the stack and nothing else: the caller fetches with `cursor.value`, reports the answer's
 * `next_cursor` through `landed()`, and refetches when `next()`/`prev()` say the page moved. A
 * changed query (filter, cluster, T, page size) must `reset()` — a stack from another query would
 * page through the wrong answer. Pairs with GridPager: `page`, `size`, `hasPrev`, `hasNext`.
 *
 * A live walk (`landed(next, true)`) holds a search on the server, and one of the user's search
 * slots, until it is closed (issue 832). The caller reads with `keep_open`, so the last page keeps
 * it too and Prev from there still works. The pager closes the walk when it drops it: on `reset()`,
 * and on Prev back to the first page, which opens a new walk.
 *
 * For a bounded row set the client already holds, use `usePagedSlice` instead.
 */
import { computed, ref } from 'vue'

import { closeCursor, holdCursor, releaseCursor } from '@/api/cursors'

export function useCursorPager(initialSize = 25) {
  const page = ref(0)
  const size = ref(initialSize)
  const cursors = ref<(string | null)[]>([null])
  const nextCursor = ref<string | null>(null)
  /** a cursor of the live walk the server holds open for this pager, closed when it is dropped */
  let held: string | null = null

  /** the cursor to send for the current page (`null` = the first page) */
  const cursor = computed(() => cursors.value[page.value] ?? null)
  const hasPrev = computed(() => page.value > 0)
  const hasNext = computed(() => nextCursor.value !== null)

  function hold(cursor: string | null) {
    if (held) releaseCursor(held)
    held = cursor
    if (cursor) holdCursor(cursor)
  }

  function drop() {
    if (held) closeCursor(held)
    held = null
  }

  /** Record the answer for the current page. `live`: a walk that holds a search on the server
   * (a findings read at T=now, or an audit read), which the pager must close when it drops it. */
  function landed(next: string | null, live = false) {
    nextCursor.value = next
    if (!live) return
    if (page.value === 0) drop() // a first page is read with no cursor: a held walk is another one
    if (next !== null) hold(next)
    // a later last page: the server kept the search (keep_open), so the walk stays held
  }

  /** Step forward; true when the page moved and the caller must fetch. */
  function next(): boolean {
    if (nextCursor.value === null) return false
    cursors.value[page.value + 1] = nextCursor.value
    page.value += 1
    nextCursor.value = null // unknown until the new page lands
    return true
  }

  /** Step back; true when the page moved and the caller must fetch. */
  function prev(): boolean {
    if (page.value === 0) return false
    if (page.value === 1) drop() // the first page is read with no cursor: it starts a new walk
    page.value -= 1
    nextCursor.value = null
    return true
  }

  function reset() {
    drop()
    page.value = 0
    cursors.value = [null]
    nextCursor.value = null
  }

  function setSize(n: number) {
    size.value = n
    reset()
  }

  return {
    page,
    size,
    cursors,
    nextCursor,
    cursor,
    hasPrev,
    hasNext,
    landed,
    next,
    prev,
    reset,
    setSize,
  }
}

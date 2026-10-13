import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/cursors', () => ({
  closeCursor: vi.fn<(cursor: string) => void>(),
  holdCursor: vi.fn<(cursor: string) => void>(),
  releaseCursor: vi.fn<(cursor: string) => void>(),
}))

import { closeCursor, holdCursor } from '@/api/cursors'
import { useCursorPager } from '@/composables/useCursorPager'

beforeEach(() => vi.clearAllMocks())

describe('useCursorPager', () => {
  it('starts on page 0 with no cursor and nowhere to go', () => {
    const p = useCursorPager(10)
    expect(p.page.value).toBe(0)
    expect(p.size.value).toBe(10)
    expect(p.cursor.value).toBeNull()
    expect(p.hasPrev.value).toBe(false)
    expect(p.hasNext.value).toBe(false)
  })

  it('walks forward on the cursors the server handed back, and back on the remembered ones', () => {
    const p = useCursorPager()
    p.landed('c1')
    expect(p.hasNext.value).toBe(true)
    expect(p.next()).toBe(true)
    expect(p.page.value).toBe(1)
    expect(p.cursor.value).toBe('c1') // cursors[i] FETCHES page i
    expect(p.hasNext.value).toBe(false) // unknown until page 1 lands

    p.landed('c2')
    expect(p.next()).toBe(true)
    expect(p.cursor.value).toBe('c2')

    expect(p.prev()).toBe(true)
    expect(p.page.value).toBe(1)
    expect(p.cursor.value).toBe('c1') // back = the cursor that fetched page 1 the first time
    expect(p.prev()).toBe(true)
    expect(p.cursor.value).toBeNull()
  })

  it('refuses to move past either end — the caller must not fetch', () => {
    const p = useCursorPager()
    expect(p.prev()).toBe(false)
    p.landed(null) // the last page
    expect(p.next()).toBe(false)
    expect(p.page.value).toBe(0)
  })

  it('reset drops the stack — another query must not page through this one', () => {
    const p = useCursorPager()
    p.landed('c1')
    p.next()
    p.landed('c2')
    p.reset()
    expect(p.page.value).toBe(0)
    expect(p.cursor.value).toBeNull()
    expect(p.hasNext.value).toBe(false)
  })

  it('a new page size starts over from page 0', () => {
    const p = useCursorPager(10)
    p.landed('c1')
    p.next()
    p.setSize(50)
    expect(p.size.value).toBe(50)
    expect(p.page.value).toBe(0)
    expect(p.cursor.value).toBeNull()
  })

  describe('a live walk (issue 832)', () => {
    /** a live walk walked to its last page: c1 fetches page 1, c2 page 2, which is the last */
    function walkedToTheEnd() {
      const p = useCursorPager()
      p.landed('c1', true)
      p.next()
      p.landed('c2', true)
      p.next()
      p.landed(null, true) // the last page: kept open by keep_open, so still held
      return p
    }

    it('is held while it pages, and Prev from its last page reuses the kept cursor', () => {
      const p = walkedToTheEnd()
      expect(holdCursor).toHaveBeenLastCalledWith('c2')
      expect(p.prev()).toBe(true)
      expect(p.cursor.value).toBe('c1') // the search is still open, so this page reads again
      expect(closeCursor).not.toHaveBeenCalled()
    })

    it('is closed on reset, filter or sort or size or cluster or T', () => {
      const p = walkedToTheEnd()
      p.reset()
      expect(closeCursor).toHaveBeenCalledExactlyOnceWith('c2')
      p.reset() // nothing held any more
      expect(closeCursor).toHaveBeenCalledOnce()
    })

    it('is closed on Prev back to the first page, which starts a new walk', () => {
      const p = useCursorPager()
      p.landed('c1', true)
      p.next()
      p.landed('c2', true)
      expect(p.prev()).toBe(true)
      expect(closeCursor).toHaveBeenCalledExactlyOnceWith('c2')
    })

    it('a first page read again closes the walk it replaces', () => {
      const p = useCursorPager()
      p.landed('c1', true)
      p.landed('c9', true) // the same first page, read again (a refresh): another walk
      expect(closeCursor).toHaveBeenCalledExactlyOnceWith('c1')
    })

    it('a first page that is also the last holds nothing, and a past-T walk is never closed', () => {
      const p = useCursorPager()
      p.landed(null, true) // the server closed it with its only page
      p.reset()
      p.landed('past-1') // not live: no search behind it
      p.next()
      p.reset()
      expect(holdCursor).not.toHaveBeenCalled()
      expect(closeCursor).not.toHaveBeenCalled()
    })
  })
})

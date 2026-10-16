import { describe, expect, it } from 'vitest'

import { moveKey, reorderFromDrag, restoreHidden, restoreOrder } from '@/system/columnOrder'

const KNOWN = ['a', 'b', 'c', 'd'] as const

describe('restoreOrder', () => {
  it('returns the default for null / garbage / non-arrays', () => {
    expect(restoreOrder(null, KNOWN)).toEqual(['a', 'b', 'c', 'd'])
    expect(restoreOrder('not json', KNOWN)).toEqual(['a', 'b', 'c', 'd'])
    expect(restoreOrder('{"a":1}', KNOWN)).toEqual(['a', 'b', 'c', 'd'])
    expect(restoreOrder('[]', KNOWN)).toEqual(['a', 'b', 'c', 'd'])
  })

  it('keeps the saved order, drops unknown keys, appends missing ones', () => {
    expect(restoreOrder('["c","a","zombie","b"]', KNOWN)).toEqual(['c', 'a', 'b', 'd'])
    expect(restoreOrder('["d",7,"a"]', KNOWN)).toEqual(['d', 'a', 'b', 'c'])
  })
})

describe('restoreHidden', () => {
  const DEFAULTS = ['b', 'd'] as const

  it.each([null, 'not json', '{}', '{"a":1}', '5', 'null', '"a"'])(
    'returns the default hidden set for %j (issue 881)',
    (raw) => {
      expect([...restoreHidden(raw, KNOWN, DEFAULTS)]).toEqual(['b', 'd'])
    },
  )

  it('keeps an empty list: the user shows every column', () => {
    expect(restoreHidden('[]', KNOWN, DEFAULTS).size).toBe(0)
  })

  it('keeps the saved keys and drops unknown keys and non-strings', () => {
    expect([...restoreHidden('["c","zombie",7,"a"]', KNOWN, DEFAULTS)]).toEqual(['c', 'a'])
  })
})

describe('reorderFromDrag (header drag — indexes over pinned + visible columns)', () => {
  const hidden = new Set(['b'])

  it('moves a visible key and keeps the hidden key anchored in its slot', () => {
    // rendered = [pin, pin, a, c, d]; drag "a"(2) onto "d"(4)
    expect(reorderFromDrag(KNOWN, hidden, 2, 4, 2)).toEqual(['c', 'b', 'd', 'a'])
  })

  it('drops past the end (onto a trailing pinned column) clamp to the last orderable slot', () => {
    expect(reorderFromDrag(KNOWN, hidden, 2, 9, 2)).toEqual(['c', 'b', 'd', 'a'])
  })

  it('drops into the pinned-left zone clamp to the first orderable slot', () => {
    expect(reorderFromDrag(KNOWN, hidden, 4, 0, 2)).toEqual(['d', 'b', 'a', 'c'])
  })

  it('is a no-op when the drag starts on a pinned column or lands where it started', () => {
    expect(reorderFromDrag(KNOWN, hidden, 1, 3, 2)).toBeNull()
    expect(reorderFromDrag(KNOWN, hidden, 3, 3, 2)).toBeNull()
  })
})

describe('moveKey (menu drag — indexes over the full key list)', () => {
  it('moves a key to the clamped target slot', () => {
    expect(moveKey(KNOWN, 'd', 0)).toEqual(['d', 'a', 'b', 'c'])
    expect(moveKey(KNOWN, 'a', 99)).toEqual(['b', 'c', 'd', 'a'])
  })

  it('is a no-op for unknown keys and same-slot moves', () => {
    expect(moveKey(KNOWN, 'zombie', 1)).toBeNull()
    expect(moveKey(KNOWN, 'b', 1)).toBeNull()
  })
})

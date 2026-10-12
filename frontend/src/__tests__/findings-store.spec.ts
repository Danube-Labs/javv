import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useFindingsStore, type FindingRow } from '@/stores/findings'

const row = (key: string): FindingRow =>
  ({ finding_key: key, cve_id: 'CVE-1', scanner: 'trivy' }) as unknown as FindingRow

describe('findings store (cursor-stack paging)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('stores server rows/total verbatim and stacks the next cursor', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 4291, 'cur-1')
    expect(s.rows).toHaveLength(1)
    expect(s.total).toBe(4291)
    expect(s.hasNext).toBe(true)
    expect(s.hasPrev).toBe(false)
    expect(s.activeCursor).toBeNull() // page 0 fetches with no cursor
  })

  it('walks next/prev over stored cursors — no offset, no jumps', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 100, 'cur-1')
    s.goNext()
    expect(s.page).toBe(1)
    expect(s.activeCursor).toBe('cur-1')
    s.setResult([row('b')], 100, 'cur-2')
    s.goNext()
    expect(s.activeCursor).toBe('cur-2')
    s.goPrev()
    s.goPrev()
    expect(s.page).toBe(0)
    expect(s.activeCursor).toBeNull()
    expect(s.hasPrev).toBe(false)
  })

  it('does not advance past the last page (no next cursor)', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 10, null)
    s.goNext()
    expect(s.page).toBe(0)
    expect(s.hasNext).toBe(false)
  })

  /** A second Next before page 1 lands used to step to page 2 with no cursor stacked, so the grid
   * re-fetched page 1's rows (or page 0's) under a later page number. */
  it('a second Next before the new page lands stays put', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 100, 'cur-1')
    s.goNext()
    expect(s.hasNext).toBe(false) // unknown until page 1 lands
    s.goNext()
    expect(s.page).toBe(1)
    expect(s.activeCursor).toBe('cur-1')
  })

  it('sort toggles direction on the same column, desc on a new one, and resets paging', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 100, 'cur-1')
    s.goNext()
    s.setSort('severity_rank') // same as default → toggles desc→asc
    expect(s.order).toBe('asc')
    expect(s.page).toBe(0)
    expect(s.cursors).toEqual([null])
    s.setSort('cvss') // new column → desc
    expect(s.sort).toBe('cvss')
    expect(s.order).toBe('desc')
  })

  it('setSize resets paging', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 100, 'cur-1')
    s.goNext()
    s.setSize(50)
    expect(s.size).toBe(50)
    expect(s.page).toBe(0)
    expect(s.nextCursor).toBeNull()
  })

  it('clearResults drops rows AND total (a cluster/T switch must not leave readable stale data)', () => {
    const s = useFindingsStore()
    s.setResult([row('a')], 4291, 'cur-1')
    s.goNext()
    s.clearResults()
    expect(s.rows).toEqual([])
    expect(s.total).toBe(0)
    expect(s.page).toBe(0)
    expect(s.cursors).toEqual([null])
    expect(s.nextCursor).toBeNull()
  })

  /** Before the cluster resolves no request has started, so `loading` is false with zero rows —
   * the grid must not read that as "this cluster is clean". */
  it('settled separates "no answer yet" from "the answer is zero"', () => {
    const s = useFindingsStore()
    expect(s.settled).toBe(false)
    expect(s.loading).toBe(false)
    expect(s.total).toBe(0)

    s.setResult([], 0, null)
    expect(s.settled).toBe(true)

    s.clearResults()
    expect(s.settled).toBe(false)
  })

  it('a failed read is answered, not pending', () => {
    const s = useFindingsStore()
    s.setFailed(503)
    expect(s.settled).toBe(true)
    expect(s.failed).toBe(true)
  })

  it('a refused first page drops the rows and the total; a refused later page keeps the total', () => {
    const s = useFindingsStore()
    s.setResult([{ finding_key: 'k' } as never], 435, 'cur-2')
    s.goNext()
    s.setFailed(410)
    expect([s.rows.length, s.total, s.page]).toEqual([0, 435, 1])
    s.resetPaging()
    s.setFailed(429)
    expect([s.rows.length, s.total]).toEqual([0, 0])
  })
})

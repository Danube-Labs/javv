import { describe, expect, it } from 'vitest'

import { buildFindingsQuery, type GridState } from '@/findings/buildFindingsQuery'
import { FINDINGS_FIELDS, emptySelections } from '@/filters/fields.config'

const CID = 'fcbcbe84-9da1-41fb-879e-83c3e0f995f0'
const GRID: GridState = { sort: 'severity_rank', order: 'desc', size: 25 }
const sel = (over: Record<string, string[]> = {}) => ({ ...emptySelections(FINDINGS_FIELDS), ...over })

describe('buildFindingsQuery', () => {
  it('always emits cluster_id, present=true, sort, order and size', () => {
    const q = buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID }, GRID)
    expect(q).toEqual({
      cluster_id: CID,
      present: true,
      sort: 'severity_rank',
      order: 'desc',
      size: 25,
    })
  })

  it('throws without a cluster_id (tenant read path, inherited)', () => {
    expect(() => buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: '' }, GRID)).toThrow(
      /cluster_id/,
    )
  })

  it('passes as_of through only when time-traveling (D28)', () => {
    const t = '2026-07-01T00:00:00Z'
    expect(
      buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID, as_of: t }, GRID).as_of,
    ).toBe(t)
    expect(
      buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID }, GRID),
    ).not.toHaveProperty('as_of')
  })

  it('carries the active filter selections (one builder, not two dialects)', () => {
    const q = buildFindingsQuery(
      FINDINGS_FIELDS,
      sel({ severity: ['CRITICAL'], scanner: ['trivy'], attr: ['kev'] }),
      { cluster_id: CID },
      GRID,
    )
    expect(q.severity).toEqual(['critical'])
    expect(q.scanner).toBe('trivy')
    expect(q.kev).toBe(true)
    expect(q.present).toBe(true)
  })

  it('rejects a sort field outside the server whitelist', () => {
    expect(() =>
      buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID }, {
        ...GRID,
        sort: 'assignee',
      } as unknown as GridState),
    ).toThrow(/sort must be one of/)
  })

  it('includes the cursor only when paging past the first page', () => {
    expect(
      buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID }, GRID),
    ).not.toHaveProperty('cursor')
    const q = buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID }, {
      ...GRID,
      cursor: 'abc123',
    })
    expect(q.cursor).toBe('abc123')
  })

  it('asks for the paths of each row only when the grid shows them (issue 1205)', () => {
    const on = buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID }, { ...GRID, locations: true })
    expect(on.locations).toBe(true)
    const off = buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID }, { ...GRID, locations: false })
    expect(off).not.toHaveProperty('locations')
    expect(buildFindingsQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID }, GRID)).not.toHaveProperty('locations')
  })
})

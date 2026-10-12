import { describe, expect, it } from 'vitest'

import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { FAILURE_COPY, failureKind } from '@/findings/failureCopy'
import { clusterFromQuery, foreignQuery, ownQuery, ttFromQuery, ttToQuery } from '@/system/globalUrl'

describe('accurate-error mapping (audit 343 rule 1)', () => {
  it('names the actual cause per status, rewound or not', () => {
    expect(failureKind(422, false)).toBe('bad_filter')
    expect(failureKind(422, true)).toBe('past_t') // the reader's unrecorded-filter 422
    expect(failureKind(501, false)).toBe('past_t')
    expect(failureKind(429, false)).toBe('busy')
    expect(failureKind(410, false)).toBe('expired') // a later page whose search context ended
    expect(failureKind(503, false)).toBe('backend')
    expect(failureKind(null, false)).toBe('backend')
  })

  it('every kind has copy that never blames the backend for user input', () => {
    expect(FAILURE_COPY.bad_filter).not.toMatch(/backend/i)
    expect(FAILURE_COPY.past_t).toMatch(/past point in time/)
  })
})

describe('contract guard: q minLength (audit 343 rule 2)', () => {
  it('omits under-minLength search text — the API would 422 it', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, { q: ['a'] }, { cluster_id: 'c-1' })
    expect(q).not.toHaveProperty('q')
    const ok = buildFilterQuery(FINDINGS_FIELDS, { q: ['ab'] }, { cluster_id: 'c-1' })
    expect(ok.q).toBe('ab')
  })
})

describe('the global range ⇄ URL (audit 343 rule 4)', () => {
  it('T=now + default window serialize to nothing — everyday URLs stay clean', () => {
    expect(ttToQuery(null, 30)).toEqual({})
    expect(ttToQuery('2026-07-08T23:59:59.999Z', 30)).toEqual({ t: '2026-07-08T23:59:59.999Z' })
    expect(ttToQuery(null, 1)).toEqual({ win: '1' })
  })

  it('restores from the URL; garbage degrades to defaults instead of poisoning reads', () => {
    expect(ttFromQuery({})).toBeNull()
    expect(ttFromQuery({ t: '2026-07-08T23:59:59.999Z' })).toEqual({
      t: '2026-07-08T23:59:59.999Z',
      win: 30,
    })
    expect(ttFromQuery({ t: 'garbage', win: '-5' })).toEqual({ t: null, win: 30 })
    expect(ttFromQuery({ win: '0.5' })).toEqual({ t: null, win: 0.5 })
    expect(ttFromQuery({ win: '9999' })).toEqual({ t: null, win: 365 })
  })

  it('foreignQuery/ownQuery split a screen query by OWNERSHIP, not a global allowlist', () => {
    const q = { severity: 'critical', t: '2026-07-08T00:00:00Z', win: '7', cluster: 'c-beta-1' }
    expect(foreignQuery(q, ['severity', 'q'])).toEqual({
      t: '2026-07-08T00:00:00Z',
      win: '7',
      cluster: 'c-beta-1',
    })
    expect(ownQuery(q, ['severity', 'q'])).toEqual({ severity: 'critical' })
  })

  it('a filter-sync rewrite never erases a key the screen does not own (operator order 2026-07-17)', () => {
    // the ?ctl= regression: a specimen switch (or any future foreign param) rode /findings and
    // the rewrite dropped it — the rewrite base must carry every non-owned key through
    const q = { severity: 'critical', spec: 'negation-b', t: '2026-07-08T00:00:00Z' }
    const rewrite = { ...foreignQuery(q, ['severity', 'q']), severity: 'high' }
    expect(rewrite).toEqual({ spec: 'negation-b', t: '2026-07-08T00:00:00Z', severity: 'high' })
  })

  it('ownQuery emits in ownKeys order and skips blanks — stable against toQuery() output', () => {
    expect(ownQuery({ q: 'log4j', severity: 'critical', junk: 'x' }, ['severity', 'q'])).toEqual({
      severity: 'critical',
      q: 'log4j',
    })
    expect(ownQuery({ severity: '' }, ['severity'])).toEqual({})
  })

  it('clusterFromQuery shape-checks only — existence is the cluster store’s call (issue 433)', () => {
    expect(clusterFromQuery({})).toBeNull()
    expect(clusterFromQuery({ cluster: '' })).toBeNull()
    expect(clusterFromQuery({ cluster: ['a', 'b'] })).toBeNull() // repeated key = malformed
    expect(clusterFromQuery({ cluster: ' c-beta-1 ' })).toBe('c-beta-1')
  })
})

describe('the SLA-breached lens (issue 363)', () => {
  it('the overdue flag emits overdue=true and round-trips the URL like any attr chip', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, { attr: ['overdue'] }, { cluster_id: 'c-1' })
    expect(q.overdue).toBe(true)
    const off = buildFilterQuery(FINDINGS_FIELDS, { attr: [] }, { cluster_id: 'c-1' })
    expect(off).not.toHaveProperty('overdue') // opt-in — never an implicit filter
  })
})

import { describe, expect, it } from 'vitest'

import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { hasUnrecordedFilter, refusedPair } from '@/findings/exportParams'
import { FAILURE_COPY, failureKind, readFailureCopy } from '@/findings/failureCopy'
import { clusterFromQuery, foreignQuery, nowWindowLabel, ownQuery, ttFromQuery, ttToQuery } from '@/system/globalUrl'

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

  it('any read: a 429 is busy, a 410 expired, anything else keeps the screen copy (issue 833, G2)', () => {
    expect(readFailureCopy(429, 'Contributors unavailable.')).toBe(FAILURE_COPY.busy)
    expect(readFailureCopy(410, 'Audit log unavailable.')).toBe(FAILURE_COPY.expired)
    for (const status of [500, 503, null]) {
      expect(readFailureCopy(status, 'Contributors unavailable.')).toBe('Contributors unavailable.')
    }
  })

  it('every kind has copy that never blames the backend for user input', () => {
    expect(FAILURE_COPY.bad_filter).not.toMatch(/backend/i)
    expect(FAILURE_COPY.past_t).toMatch(/at a past time/)
  })

  // issue 1294: at a past time the history answers Search, Image and Tag, so the text names only
  // the filters that still get the 422 (PAST_TIME_UNRECORDED_KEYS)
  it('the past-time text names KEV, Scanners disagree and New in range, and no search', () => {
    expect(FAILURE_COPY.past_t).toBe(
      'JAVV cannot apply the KEV, Scanners disagree or New in range filter at a past time. Go back to now, or remove these filters.',
    )
    expect(FAILURE_COPY.past_t).not.toMatch(/search/i)
  })

  // issue 975: a short search never gets to the server, so the 422 text names the causes that do
  it('a 422 names refused filters, never a short search', () => {
    expect(FAILURE_COPY.bad_filter).toBe(
      "JAVV refused the filters. Two of the filters cannot go together, or a value is not valid. Check the filters.",
    )
    expect(FAILURE_COPY.bad_filter).not.toMatch(/characters/)
  })

  it('a refused pair gets the same text at a past time as now', () => {
    expect(failureKind(422, false, true)).toBe('bad_filter')
    expect(failureKind(422, true, true)).toBe('bad_filter')
    expect(failureKind(422, true, false)).toBe('past_t') // an unrecorded filter at a past time
    expect(failureKind(501, true, true)).toBe('past_t')
  })

  // issue 1294 review: the past-time text names KEV, Scanners disagree and New in range, so it
  // shows only when the refused read holds one of them
  it('a 422 at a past time with none of those filters gets the refused-filters text', () => {
    expect(failureKind(422, true, false, false)).toBe('bad_filter')
    expect(failureKind(422, true, false, true)).toBe('past_t')
    expect(hasUnrecordedFilter({ cluster_id: 'c', severity: ['high'] })).toBe(false)
    expect(hasUnrecordedFilter({ cluster_id: 'c', kev: true })).toBe(true)
    expect(hasUnrecordedFilter({ cluster_id: 'c', new_within_days: 7 })).toBe(true)
  })

  it('finds each refused pair in a built query, and only the include side', () => {
    const globals = { cluster_id: 'c-1' }
    const both = buildFilterQuery(FINDINGS_FIELDS, { assignee: ['bob'], attr: ['unassigned'] }, globals)
    expect(refusedPair(both)).toEqual(['assignee', 'unassigned'])
    const notSide = buildFilterQuery(
      FINDINGS_FIELDS,
      { assignee: ['bob'], attr: ['unassigned'] },
      globals,
      { assignee: 'not' },
    )
    expect(refusedPair(notSide)).toBeNull()
    expect(refusedPair(buildFilterQuery(FINDINGS_FIELDS, { attr: ['unassigned'] }, globals))).toBeNull()
    // issue 1294: Tag with No tag, the second pair
    const tags = buildFilterQuery(FINDINGS_FIELDS, { tag: ['1.4.1'], attr: ['untagged'] }, globals)
    expect(refusedPair(tags)).toEqual(['tag', 'untagged'])
    const tagNot = buildFilterQuery(FINDINGS_FIELDS, { tag: ['1.4.1'], attr: ['untagged'] }, globals, { tag: 'not' })
    expect(refusedPair(tagNot)).toBeNull()
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

  it.each([
    [30, 'Last 30 days'],
    [1, 'Last 1 day'],
    [3.4, 'Last 3.4 days'],
    [2.0005, 'Last 2 days'], // a typed 2 days, to the second of now
    [1.4167, 'Last 34 hours'], // an Exact range of 34 hours, in the 4 decimals of the URL (issue 1313)
    [1.5, 'Last 36 hours'],
    [0.0833, 'Last 2 hours'],
    [0.0208, 'Last 30 minutes'],
    [0.0007, 'Last 1 minute'],
  ])('a URL range of %f days at now reads "%s" after a reload', (win, label) => {
    expect(nowWindowLabel(win)).toBe(label)
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

/**
 * A value of a fixed list with no rows shows 0 (issue 980). A terms aggregation gives no bucket
 * for a value with no rows, so the rail showed no count for it, while SLA breached and
 * Unassigned (filter aggregations) showed 0. The prototype shows each 0. A count stays unknown
 * when the server did not count the field, or stopped at FACET_CAP buckets before the value.
 */
import { describe, expect, it } from 'vitest'

import { AUDIT_ACTIONS, AUDIT_FIELDS } from '@/audit/fields.config'
import { FACET_CAP, facetItems, type FacetBucket, type FacetsResponse } from '@/filters/facets'
import { FINDINGS_FIELDS, type FilterField } from '@/filters/fields.config'

const field = (fields: readonly FilterField[], key: string) => fields.find((f) => f.key === key)!
const ATTR = field(FINDINGS_FIELDS, 'attr')
const SEVERITY = field(FINDINGS_FIELDS, 'severity')
const NAMESPACE = field(FINDINGS_FIELDS, 'namespace')
const ACTION = field(AUDIT_FIELDS, 'action')

const b = (key: string, count: number): FacetBucket => ({ key, count, by_scanner: { trivy: count } })
const countsOf = (items: ReturnType<typeof facetItems>) =>
  Object.fromEntries((items ?? []).map((i) => [i.value, i.count]))

describe('a count of 0 on a fixed list (issue 980)', () => {
  it('a flag the server counted with no "true" bucket shows 0; one it did not count shows none', () => {
    const facets: FacetsResponse = {
      kev: [b('false', 29)],
      fixable: [b('true', 14), b('false', 15)],
      disagree: [],
      overdue: [b('true', 21)],
      unassigned: [b('true', 0)],
    }
    expect(countsOf(facetItems(ATTR, facets))).toEqual({
      kev: 0,
      fixable: 14,
      disagree: 0,
      overdue: 21,
      unassigned: 0,
      new: null, // New in range has no facet: the server never counts it
    })
  })

  it('a severity with no bucket shows 0, with no scanner split', () => {
    const items = facetItems(SEVERITY, { severity: [b('critical', 29)] })!
    expect(countsOf(items)).toEqual({ critical: 29, high: 0, medium: 0, low: 0, negligible: 0, unknown: 0 })
    expect(items.find((i) => i.value === 'high')!.byScanner).toEqual({})
  })

  it('a field missing from the response keeps no count', () => {
    // the first read has not come back, or the screen does not ask for the field
    expect(Object.values(countsOf(facetItems(SEVERITY, {})))).toEqual(Array(6).fill(null))
    expect(Object.values(countsOf(facetItems(ATTR, {})))).toEqual(Array(6).fill(null))
  })

  it(`an Action list the server stopped at ${FACET_CAP} buckets keeps no count for the rest`, () => {
    // the audit route counts the top 32 actions, and the list has more: an action outside the
    // top 32 has rows the server did not count, so a 0 there would be false
    expect(AUDIT_ACTIONS.length).toBeGreaterThan(FACET_CAP)
    const top = AUDIT_ACTIONS.slice(0, FACET_CAP).map((a, i) => b(a, 100 - i))
    const items = facetItems(ACTION, { action: top })!
    const rest = items.filter((i) => !top.some((t) => t.key === i.value))
    expect(rest.length).toBe(AUDIT_ACTIONS.length - FACET_CAP)
    expect(rest.every((i) => i.count === null)).toBe(true)
    expect(items.filter((i) => i.count !== null)).toHaveLength(FACET_CAP)
  })

  it('an Action list under the cap shows 0 for each action with no events', () => {
    const items = facetItems(ACTION, { action: [b('login', 3)] })!
    expect(items.find((i) => i.value === 'login')!.count).toBe(3)
    expect(items.filter((i) => i.count === 0)).toHaveLength(AUDIT_ACTIONS.length - 1)
  })

  it('a list with no fixed values lists only the server buckets, as before', () => {
    const items = facetItems(NAMESPACE, { namespaces: [b('shop', 2)] }, ['shop', 'edge'])!
    expect(items.map((i) => [i.value, i.count])).toEqual([
      ['shop', 2],
      ['edge', null], // a picked value the buckets leave out has no count (issue 949)
    ])
  })
})

/**
 * A value of a fixed list with no rows shows 0 (issue 980). A terms aggregation gives no bucket
 * for a value with no rows, so the rail showed no count for it, while SLA breached and
 * Unassigned (filter aggregations) showed 0. The prototype shows each 0. A count stays unknown
 * when the server did not count the field, or stopped at the cap of the field before the value
 * (FACET_CAP, or the field's own `facetCap`, issue 983).
 */
import { describe, expect, it } from 'vitest'

import { AUDIT_ACTIONS, AUDIT_FIELDS, AUDIT_LIST_CAP } from '@/audit/fields.config'
import {
  FACET_CAP,
  facetItems,
  searchItems,
  stoppedAtCap,
  type FacetBucket,
  type FacetsResponse,
} from '@/filters/facets'
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

  it(`a fixed list the server stopped at ${FACET_CAP} buckets keeps no count for the rest`, () => {
    // a value outside the buckets has rows the server did not count, so a 0 there would be false
    const values = Array.from({ length: 40 }, (_, i) => `v-${i}`)
    const FIXED: FilterField = { key: 'fixed', label: 'Fixed', type: 'terms', param: 'fixed', facetKey: 'fixed', values }
    const top = values.slice(0, FACET_CAP).map((v, i) => b(v, 100 - i))
    const items = facetItems(FIXED, { fixed: top })!
    expect(items.filter((i) => i.count !== null)).toHaveLength(FACET_CAP)
    expect(items.slice(FACET_CAP).every((i) => i.count === null)).toBe(true)
  })

  it(`the Action list counts up to ${AUDIT_LIST_CAP} buckets, so each action has a count (issue 983)`, () => {
    // the server gives the Action count AUDIT_LIST_CAP buckets: at 40 actions with events, the
    // other actions have no events, so they show 0, not an unknown count
    expect(AUDIT_ACTIONS.length).toBeGreaterThan(FACET_CAP)
    expect(AUDIT_ACTIONS.length).toBeLessThan(AUDIT_LIST_CAP)
    const forty = AUDIT_ACTIONS.slice(0, 40).map((a, i) => b(a, 100 - i))
    const items = facetItems(ACTION, { action: forty })!
    expect(items.every((i) => i.count !== null)).toBe(true)
    expect(items.filter((i) => i.count === 0)).toHaveLength(AUDIT_ACTIONS.length - 40)
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

/** Issue 1064: a list the server stopped at its cap can leave out the value a user wants, so the
 * menu asks the server for the values that contain the typed text. */
describe('a list that stopped at its cap (issue 1064)', () => {
  const many = (n: number) => Array.from({ length: n }, (_, i) => b(`ns-${i}`, 100 - i))

  it(`stopped at ${FACET_CAP} buckets, not at ${FACET_CAP - 1}`, () => {
    expect(stoppedAtCap(NAMESPACE, { namespaces: many(FACET_CAP) })).toBe(true)
    expect(stoppedAtCap(NAMESPACE, { namespaces: many(FACET_CAP - 1) })).toBe(false)
    expect(stoppedAtCap(NAMESPACE, {})).toBe(false) // the server did not count the field
  })

  it('a flag field or a text field never stops at a cap', () => {
    expect(stoppedAtCap(ATTR, { kev: many(FACET_CAP) })).toBe(false)
    expect(stoppedAtCap(field(FINDINGS_FIELDS, 'cve'), {})).toBe(false)
  })

  it(`the Action list stops at its own cap of ${AUDIT_LIST_CAP}, not at ${FACET_CAP}`, () => {
    expect(stoppedAtCap(ACTION, { action: many(FACET_CAP) })).toBe(false)
    expect(stoppedAtCap(ACTION, { action: many(AUDIT_LIST_CAP) })).toBe(true)
  })

  it('the items of a search keep the server order, counts and scanner split', () => {
    const items = searchItems(NAMESPACE, [b('pay-2', 9), b('pay-1', 3)])
    expect(items.map((i) => [i.value, i.count, i.byScanner])).toEqual([
      ['pay-2', 9, { trivy: 9 }],
      ['pay-1', 3, { trivy: 3 }],
    ])
  })
})

import { describe, expect, it } from 'vitest'

import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { FINDINGS_FIELDS, emptySelections, type FilterField } from '@/filters/fields.config'

const CID = 'fcbcbe84-9da1-41fb-879e-83c3e0f995f0'
const sel = (over: Record<string, string[]> = {}) => ({ ...emptySelections(FINDINGS_FIELDS), ...over })

describe('buildFilterQuery', () => {
  it('always emits cluster_id, even with no selections', () => {
    expect(buildFilterQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID })).toEqual({ cluster_id: CID })
  })

  it('throws when cluster_id is missing (tenant read path)', () => {
    expect(() => buildFilterQuery(FINDINGS_FIELDS, sel(), { cluster_id: '' })).toThrow(/cluster_id/)
  })

  it('omits as_of at T=now and passes it through when time-traveling (D28)', () => {
    expect(buildFilterQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID })).not.toHaveProperty('as_of')
    const t = '2026-07-01T00:00:00Z'
    expect(buildFilterQuery(FINDINGS_FIELDS, sel(), { cluster_id: CID, as_of: t }).as_of).toBe(t)
  })

  it('emits multi-value terms as arrays, lowercased (D16 severity case-insensitive)', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ severity: ['CRITICAL', 'negligible'] }), {
      cluster_id: CID,
    })
    expect(q.severity).toEqual(['critical', 'negligible'])
  })

  it('emits single-value terms as scalars and refuses to merge two selections', () => {
    expect(
      buildFilterQuery(FINDINGS_FIELDS, sel({ scanner: ['trivy'] }), { cluster_id: CID }).scanner,
    ).toBe('trivy')
    expect(() =>
      buildFilterQuery(FINDINGS_FIELDS, sel({ scanner: ['trivy', 'grype'] }), { cluster_id: CID }),
    ).toThrow(/single value/)
  })

  it('maps selected flags to their own boolean params', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ attr: ['kev', 'disagree'] }), { cluster_id: CID })
    expect(q.kev).toBe(true)
    expect(q.disagree).toBe(true)
    expect(q).not.toHaveProperty('fixable')
  })

  it('trims text fields and drops blank ones', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ image: ['  nginx  '] }), {
      cluster_id: CID,
    })
    expect(q.image_repo).toEqual(['nginx']) // a list since issue 949 PR C
    const blank = buildFilterQuery(FINDINGS_FIELDS, sel({ image: ['   '] }), { cluster_id: CID })
    expect(blank).not.toHaveProperty('image_repo')
  })

  // issue 949: the three list facets take several values, so they always emit an array
  it('namespace, package type and assignee emit arrays, one value or several', () => {
    const one = buildFilterQuery(FINDINGS_FIELDS, sel({ namespace: ['payments'], assignee: ['admin'] }), {
      cluster_id: CID,
    })
    expect(one.namespace).toEqual(['payments'])
    expect(one.assignee).toEqual(['admin'])
    const two = buildFilterQuery(
      FINDINGS_FIELDS,
      sel({ namespace: ['payments', 'edge'], ptype: ['debian', 'npm'], assignee: ['ana', 'bob'] }),
      { cluster_id: CID },
    )
    expect(two.namespace).toEqual(['payments', 'edge'])
    expect(two.ptype).toEqual(['debian', 'npm'])
    expect(two.assignee).toEqual(['ana', 'bob'])
  })

  it('several excluded values go to the exclude_* param as one array', () => {
    const q = buildFilterQuery(
      FINDINGS_FIELDS,
      sel({ namespace: ['payments', 'edge'], ptype: ['debian', 'npm'], assignee: ['ana', 'bob'] }),
      { cluster_id: CID },
      { namespace: 'not', ptype: 'not', assignee: 'not' },
    )
    expect(q.exclude_namespace).toEqual(['payments', 'edge'])
    expect(q.exclude_ptype).toEqual(['debian', 'npm'])
    expect(q.exclude_assignee).toEqual(['ana', 'bob'])
    expect(q).not.toHaveProperty('namespace')
  })

  it('the "new" window flag emits the picker days (API-clamped), never a bare true', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ attr: ['new'] }), {
      cluster_id: CID,
      window_days: 30,
    })
    expect(q.new_within_days).toBe(30)
    // sub-day windows round up to the day-grained 1..365 contract, like the trend charts
    const day = buildFilterQuery(FINDINGS_FIELDS, sel({ attr: ['new'] }), {
      cluster_id: CID,
      window_days: 0.0625,
    })
    expect(day.new_within_days).toBe(1)
    // and it refuses to guess a window
    expect(() =>
      buildFilterQuery(FINDINGS_FIELDS, sel({ attr: ['new'] }), { cluster_id: CID }),
    ).toThrow(/window_days/)
  })

  it('negation (issue 349): a not-mode terms field emits its exclude_* mirror param', () => {
    const q = buildFilterQuery(
      FINDINGS_FIELDS,
      sel({ severity: ['LOW', 'negligible'], namespace: ['kube-system'], state: ['open'] }),
      { cluster_id: CID },
      { severity: 'not', namespace: 'not' },
    )
    expect(q.exclude_severity).toEqual(['low', 'negligible']) // lowercased like the include side
    expect(q.exclude_namespace).toEqual(['kube-system'])
    expect(q.state).toEqual(['open']) // is-mode fields keep their include param
    expect(q).not.toHaveProperty('severity')
    expect(q).not.toHaveProperty('namespace')
  })

  /** `image_repo` is an exact `term` server-side and has an `exclude_image_repo` twin, so a
   * TEXT field negates like a terms one — the input is the entry affordance, not the match. */
  it('negation reaches text fields that declare an exclude twin', () => {
    const q = buildFilterQuery(
      FINDINGS_FIELDS,
      sel({ image: ['docker.io/library/nginx'] }),
      { cluster_id: CID },
      { image: 'not' },
    )
    expect(q.exclude_image_repo).toEqual(['docker.io/library/nginx'])
    expect(q).not.toHaveProperty('image_repo')
  })

  /** Issue 492 closed the negation family: `cve_id` and `package_name` are the last two, both
   *  exact terms server-side and both bar-and-cell fields (neither is a facet). */
  it('cve and package emit their own params in both directions', () => {
    const inc = buildFilterQuery(
      FINDINGS_FIELDS,
      sel({ cve: ['CVE-2021-3711'], package: ['zlib'] }),
      { cluster_id: CID },
    )
    expect(inc.cve_id).toEqual(['CVE-2021-3711'])
    expect(inc.package_name).toEqual(['zlib'])

    const exc = buildFilterQuery(
      FINDINGS_FIELDS,
      sel({ cve: ['CVE-2021-3711'], package: ['zlib'] }),
      { cluster_id: CID },
      { cve: 'not', package: 'not' },
    )
    expect(exc.exclude_cve_id).toEqual(['CVE-2021-3711'])
    expect(exc.exclude_package_name).toEqual(['zlib'])
    // a field is include OR exclude — the mirror replaces the param, never doubles it
    expect(exc).not.toHaveProperty('cve_id')
    expect(exc).not.toHaveProperty('package_name')
  })

  // issue 949 PR C: Image, CVE and Package take several typed values
  it('typed values go out as one list, trimmed, blanks dropped, in both modes', () => {
    const inc = buildFilterQuery(FINDINGS_FIELDS, sel({ image: [' api ', '   ', 'web'] }), { cluster_id: CID })
    expect(inc.image_repo).toEqual(['api', 'web'])
    const exc = buildFilterQuery(
      FINDINGS_FIELDS,
      sel({ cve: ['CVE-1', 'CVE-2'] }),
      { cluster_id: CID },
      { cve: 'not' },
    )
    expect(exc.exclude_cve_id).toEqual(['CVE-1', 'CVE-2'])
    expect(exc).not.toHaveProperty('cve_id')
  })

  it('a text field with no exclude twin ignores the mode entirely', () => {
    const q = buildFilterQuery(FINDINGS_FIELDS, sel({ q: ['nginx'] }), { cluster_id: CID }, { q: 'not' })
    expect(q.q).toBe('nginx') // the rail search box is not negatable
    expect(q).not.toHaveProperty('exclude_q')
  })

  it('drives entirely off the config: a new field needs no builder change', () => {
    const fields: FilterField[] = [
      ...FINDINGS_FIELDS,
      { key: 'os', label: 'OS', type: 'terms', param: 'os_name', multi: true },
    ]
    const q = buildFilterQuery(fields, { ...sel(), os: ['Alpine'] }, { cluster_id: CID })
    expect(q.os_name).toEqual(['alpine'])
  })
})

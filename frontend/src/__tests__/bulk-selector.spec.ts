/**
 * The lens→selector safety contract: bulk NEVER applies wider than the visible lens — an
 * inexpressible or multi-value or empty lens blocks with the reason instead of widening.
 */
import { describe, expect, it } from 'vitest'

import { emptySelections, FINDINGS_FIELDS } from '@/filters/fields.config'
import { lensToSelector } from '@/findings/bulkSelector'

function sel(over: Record<string, string[]> = {}) {
  return { ...emptySelections(FINDINGS_FIELDS), ...over }
}

describe('lensToSelector (bulk never widens the lens)', () => {
  it('blocks on an excluded field (issue 349) — the selector has no exclude side', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['low'] }), { severity: 'not' })
    expect(r.selector).toBeNull()
    expect(r.blocked).toMatch(/Severity \(excluded\)/)
  })

  it('maps single-value severity/state/assignee to the selector', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical'], state: ['open'], assignee: ['admin'] }))
    expect(r.blocked).toBeNull()
    expect(r.selector).toEqual({ severity: 'critical', state: 'open', assignee: 'admin' })
  })

  it('blocks on filters the selector cannot express (scanner, flags, namespace, image, ptype)', () => {
    const lenses: Record<string, string[]>[] = [
      { scanner: ['trivy'] },
      { attr: ['kev'] },
      { namespace: ['payments'] },
      { image: ['nginx'] },
      { ptype: ['deb'] },
    ]
    for (const active of lenses) {
      const r = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical'], ...active }))
      expect(r.selector).toBeNull()
      expect(r.blocked).toMatch(/^Remove (this filter|these filters) first: /)
      expect(r.blocked).toMatch(/more findings than you see/)
    }
  })

  it('blocks multi-value severity/state (the selector takes exactly one)', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical', 'high'] }))
    expect(r.selector).toBeNull()
    expect(r.blocked).toMatch(/exactly one/)
  })

  // issue 949: assignee takes several values now; the selector still takes exactly one
  it('blocks two assignees, as it blocks two severities', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical'], assignee: ['ana', 'bob'] }))
    expect(r.selector).toBeNull()
    expect(r.blocked).toBe('Pick a single Assignee value. Bulk triage works on exactly one at a time.')
  })

  it('refuses an empty lens — whole-cluster bulk is never offered', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel())
    expect(r.selector).toBeNull()
    expect(r.blocked).toMatch(/^Add a filter first\./)
  })
})

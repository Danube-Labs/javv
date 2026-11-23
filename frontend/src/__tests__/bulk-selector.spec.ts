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

  // issue 1294: the selector has no tag, so the Tag filter and No tag block, as Image does
  it('blocks on the Tag filter and on No tag', () => {
    const tag = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical'], tag: ['1.4.1'] }))
    expect(tag.selector).toBeNull()
    expect(tag.blocked).toMatch(/^Remove this filter first: Tag\. /)
    const excluded = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical'], tag: ['latest'] }), { tag: 'not' })
    expect(excluded.blocked).toMatch(/^Remove this filter first: Tag \(excluded\)\. /)
    const untagged = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical'], attr: ['untagged'] }))
    expect(untagged.selector).toBeNull()
    expect(untagged.blocked).toMatch(/^Remove this filter first: Attribute\. /)
  })

  it('blocks multi-value severity/state (the selector takes exactly one)', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical', 'high'] }))
    expect(r.selector).toBeNull()
    expect(r.blocked).toMatch(/one value at a time/)
  })

  // issue 949: assignee takes several values now; the selector still takes exactly one
  it('blocks two assignees, as it blocks two severities', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical'], assignee: ['ana', 'bob'] }))
    expect(r.selector).toBeNull()
    expect(r.blocked).toBe('Select one Assignee value only. Bulk triage uses one value at a time.')
  })

  it('refuses an empty lens — whole-cluster bulk is never offered', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel())
    expect(r.selector).toBeNull()
    expect(r.blocked).toMatch(/^Add a filter first\./)
  })
})

// The image page opens Findings on one digest (issue 1140). The bulk selector of the backend
// takes image_digest, so a digest filter narrows a bulk change instead of blocking it.
describe('lensToSelector with the Digest filter', () => {
  it('maps the digest to image_digest, next to a severity', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel({ severity: ['critical'], digest: ['sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1'] }))
    expect(r).toEqual({ selector: { severity: 'critical', image_digest: 'sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1' }, blocked: null })
  })

  it('a digest alone is a selector', () => {
    expect(lensToSelector(FINDINGS_FIELDS, sel({ digest: ['sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1'] })).selector).toEqual({ image_digest: 'sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1' })
  })

  it('still blocks with a scanner filter next to the digest, since the selector has no scanner', () => {
    const r = lensToSelector(FINDINGS_FIELDS, sel({ digest: ['sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1'], scanner: ['trivy'] }))
    expect(r.selector).toBeNull()
    expect(r.blocked).toContain('Scanner')
  })
})

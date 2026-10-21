import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { AUDIT_FIELDS } from '@/audit/fields.config'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { makeFiltersStore } from '@/stores/filters'

const useStore = makeFiltersStore('test-filters', FINDINGS_FIELDS)
const useAuditStore = makeFiltersStore('test-audit-filters', AUDIT_FIELDS)

describe('filters store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('toggles multi-value terms on and off', () => {
    const s = useStore()
    s.toggle('severity', 'critical')
    s.toggle('severity', 'high')
    expect(s.selections.severity).toEqual(['critical', 'high'])
    s.toggle('severity', 'critical')
    expect(s.selections.severity).toEqual(['high'])
    expect(s.hasFilters).toBe(true)
  })

  it('replaces instead of accumulating on single-value terms', () => {
    const s = useStore()
    s.toggle('scanner', 'trivy')
    s.toggle('scanner', 'grype')
    expect(s.selections.scanner).toEqual(['grype'])
  })

  // issue 949: the three list facets of the Findings rail take several values
  it.each(['namespace', 'ptype', 'assignee'])('a second %s pick adds the value', (field) => {
    const s = useStore()
    s.toggle(field, 'one')
    s.toggle(field, 'two')
    expect(s.selections[field]).toEqual(['one', 'two'])
    s.toggle(field, 'one')
    expect(s.selections[field]).toEqual(['two'])
  })

  it('several namespaces, package types and assignees round-trip the URL in both modes', () => {
    const s = useStore()
    s.toggle('namespace', 'payments')
    s.toggle('namespace', 'edge')
    s.pickValue('ptype', 'debian', 'not')
    s.pickValue('ptype', 'npm', 'not')
    s.toggle('assignee', 'ana')
    s.toggle('assignee', 'bob')
    const query = s.toQuery()
    expect(query).toMatchObject({
      namespace: 'payments,edge',
      ptype: '!debian,!npm',
      assignee: 'ana,bob',
    })
    s.clearAll()
    s.fromQuery(query)
    expect(s.selections.namespace).toEqual(['payments', 'edge'])
    expect(s.selections.ptype).toEqual(['debian', 'npm'])
    expect(s.modeOf('ptype')).toBe('not')
    expect(s.selections.assignee).toEqual(['ana', 'bob'])
  })

  it('clearField and clearAll empty the selections', () => {
    const s = useStore()
    s.toggle('severity', 'low')
    s.setText('namespace', 'payments')
    s.clearField('severity')
    expect(s.selections.severity).toEqual([])
    expect(s.hasFilters).toBe(true)
    s.clearAll()
    expect(s.hasFilters).toBe(false)
  })

  it('round-trips selections through the URL query unchanged (bolt DoD)', () => {
    const s = useStore()
    s.toggle('severity', 'critical')
    s.toggle('severity', 'negligible')
    s.toggle('attr', 'kev')
    s.toggle('scanner', 'trivy')
    s.setText('namespace', 'payments')
    const snapshot = JSON.parse(JSON.stringify(s.selections))

    const query = s.toQuery()
    expect(query).toEqual({
      severity: 'critical,negligible',
      attr: 'kev',
      scanner: 'trivy',
      namespace: 'payments',
    })

    s.clearAll()
    s.fromQuery(query)
    expect(s.selections).toEqual(snapshot)
  })

  it('negation (issue 349): mode round-trips the URL as ! prefixes, one mode per field', () => {
    const s = useStore()
    s.toggle('severity', 'low')
    s.toggle('severity', 'negligible')
    s.setMode('severity', 'not')
    expect(s.toQuery().severity).toBe('!low,!negligible')
    s.clearAll()
    s.fromQuery({ severity: '!low,!negligible', namespace: 'payments' })
    expect(s.selections.severity).toEqual(['low', 'negligible'])
    expect(s.modeOf('severity')).toBe('not')
    expect(s.modeOf('namespace')).toBe('is') // untouched fields stay include
  })

  it('negation guards: non-negatable fields refuse the mode; clearing resets it', () => {
    const s = useStore()
    s.setMode('attr', 'not') // flags are never negatable
    expect(s.modeOf('attr')).toBe('is')
    s.toggle('namespace', 'kube-system')
    s.setMode('namespace', 'not')
    expect(s.toQuery().namespace).toBe('!kube-system')
    s.clearField('namespace')
    expect(s.modeOf('namespace')).toBe('is')
    s.toggle('namespace', 'kube-system')
    expect(s.toQuery().namespace).toBe('kube-system') // mode did not survive the clear
  })

  /** The rail/grid value actions (issue 349 §2) — pick a value straight into a mode. */
  // issue 949 PR C: Image, CVE and Package keep several typed values
  it('keeps several typed values across the URL; a one-value text field keeps one', () => {
    const s = useStore()
    s.fromQuery({ image: 'api,web', q: 'curl,wget' })
    expect(s.selections.image).toEqual(['api', 'web'])
    expect(s.selections.q).toEqual(['curl'])
    expect(s.toQuery().image).toBe('api,web')
  })

  describe('pickValue', () => {
    it('excludes in one action, where before it took a toggle plus a pill flip', () => {
      const s = useStore()
      s.pickValue('namespace', 'kube-system', 'not')
      expect(s.selections.namespace).toEqual(['kube-system'])
      expect(s.modeOf('namespace')).toBe('not')
      expect(s.toQuery().namespace).toBe('!kube-system')
    })

    it('clicking the side a value already sits on clears it, mode included', () => {
      const s = useStore()
      s.pickValue('namespace', 'kube-system', 'not')
      s.pickValue('namespace', 'kube-system', 'not')
      expect(s.selections.namespace).toEqual([])
      expect(s.modeOf('namespace')).toBe('is') // no orphan mode on an empty field
      expect(s.toQuery()).not.toHaveProperty('namespace')
    })

    it('accumulates within a mode on multi-value fields', () => {
      const s = useStore()
      s.pickValue('severity', 'low', 'not')
      s.pickValue('severity', 'negligible', 'not')
      expect(s.toQuery().severity).toBe('!low,!negligible')
    })

    /** A field carries ONE mode, so the values cannot come along — their meaning would invert. */
    it('switching a field to the other mode starts a fresh selection', () => {
      const s = useStore()
      s.pickValue('severity', 'critical', 'is')
      s.pickValue('severity', 'high', 'is')
      expect(s.selections.severity).toEqual(['critical', 'high'])
      s.pickValue('severity', 'low', 'not')
      expect(s.selections.severity).toEqual(['low'])
      expect(s.modeOf('severity')).toBe('not')
    })

    it('refuses exclude where the backend has no exclude_* twin', () => {
      const s = useStore()
      s.pickValue('attr', 'kev', 'not') // flags are never negatable — absence ≠ negation
      expect(s.selections.attr).toEqual([])
      expect(s.modeOf('attr')).toBe('is')
      s.pickValue('q', 'nginx', 'not') // the rail search box declares no exclude twin
      expect(s.selections.q).toEqual([])
    })

    /** `image_repo` is an exact `term` server-side with an `exclude_image_repo` twin, so a
     * TEXT field can negate — the free-text input is the entry affordance, not the match. */
    it('negates a text field that declares an exclude twin', () => {
      const s = useStore()
      s.pickValue('image', 'docker.io/library/nginx', 'not')
      expect(s.selections.image).toEqual(['docker.io/library/nginx'])
      expect(s.modeOf('image')).toBe('not')
      expect(s.toQuery().image).toBe('!docker.io/library/nginx')
      // one value per text field — picking the same side again clears rather than accumulates
      s.pickValue('image', 'docker.io/library/nginx', 'not')
      expect(s.selections.image).toEqual([])
      expect(s.modeOf('image')).toBe('is')
    })
  })

  it('drops unknown vocabulary values and unknown keys from the URL', () => {
    const s = useStore()
    s.fromQuery({ severity: 'critical,BOGUS', attr: 'kev,nope', evil: 'x' })
    expect(s.selections.severity).toEqual(['critical'])
    expect(s.selections.attr).toEqual(['kev'])
    expect(s.selections).not.toHaveProperty('evil')
  })

  /** Canned lens links hand a URL to a screen that was not the one that built it. `?action=login`
   * (the recent-sign-ins link on admin/users) only lands if the key matches the field key AND the
   * value is in the vocabulary — the test above proves an unknown value is silently DROPPED, so a
   * renamed key or a trimmed AUDIT_ACTIONS would leave the link opening an unfiltered log. */
  it('the recent-sign-ins lens URL is one the audit filter store actually applies', () => {
    const s = useAuditStore()
    s.fromQuery({ action: 'login' })
    expect(s.selections.action).toEqual(['login'])
    expect(s.modeOf('action')).toBe('is')
    expect(s.hasFilters).toBe(true)
    // and it round-trips: the screen re-emits the same URL it was opened with
    expect(s.toQuery()).toEqual({ action: 'login' })
  })
})

describe('filters store — a table cell adds a typed value (issue 949 PR C)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('a second image from a cell adds it; the same one again takes it out', () => {
    const s = useStore()
    s.pickValue('image', 'api', 'is')
    s.pickValue('image', 'web', 'is')
    expect(s.selections.image).toEqual(['api', 'web'])
    s.pickValue('image', 'api', 'is')
    expect(s.selections.image).toEqual(['web'])
  })

  it('a pick in the other mode starts over with that value, as for a terms field', () => {
    const s = useStore()
    s.pickValue('cve', 'CVE-1', 'is')
    s.pickValue('cve', 'CVE-2', 'is')
    s.pickValue('cve', 'CVE-3', 'not')
    expect(s.selections.cve).toEqual(['CVE-3'])
    expect(s.modeOf('cve')).toBe('not')
  })
})

describe('filters store — the API cap of 32 values (issue 949)', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('a URL with more values keeps the first 32', () => {
    const s = useStore()
    const many = Array.from({ length: 40 }, (_, i) => `ns-${i}`)
    s.fromQuery({ namespace: many.join(','), cve: many.join(',') })
    expect(s.selections.namespace).toHaveLength(32)
    expect(s.selections.cve).toHaveLength(32)
  })

  it('a 33rd pick adds nothing', () => {
    const s = useStore()
    for (let i = 0; i < 33; i++) s.pickValue('image', `img-${i}`, 'is')
    expect(s.selections.image).toHaveLength(32)
    expect(s.selections.image).not.toContain('img-32')
  })
})

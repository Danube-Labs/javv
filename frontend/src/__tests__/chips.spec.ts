import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import CountDisagree from '@/components/chips/CountDisagree.vue'
import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import EpssBar from '@/components/chips/EpssBar.vue'
import KevTag from '@/components/chips/KevTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import SlaCell from '@/components/chips/SlaCell.vue'
import StateTag from '@/components/chips/StateTag.vue'
import { SEVERITIES } from '@/styles/tokens'

describe('SevChip', () => {
  it('renders every D46 canonical with its own data-sev bucket, uppercased for display (A-1)', () => {
    for (const sev of SEVERITIES) {
      const w = mount(SevChip, { props: { level: sev } })
      expect(w.attributes('data-sev')).toBe(sev)
      expect(w.text()).toBe(sev.toUpperCase())
    }
  })

  it('falls back to the unknown bucket for out-of-vocabulary input', () => {
    const w = mount(SevChip, { props: { level: 'SUPERBAD' } })
    expect(w.attributes('data-sev')).toBe('unknown')
  })
})

describe('StateTag', () => {
  it('labels all six states of the shipped model (A-2)', () => {
    const expected: Record<string, string> = {
      open: 'Open',
      stale: 'Stale',
      acknowledged: 'Acknowledged',
      not_affected: 'Not affected',
      risk_accepted: 'Risk accepted',
      resolved: 'Resolved',
    }
    for (const [state, label] of Object.entries(expected)) {
      const w = mount(StateTag, { props: { state } })
      expect(w.text()).toBe(label)
      expect(w.attributes('data-state')).toBe(state)
    }
  })
})

describe('KevTag / EpssBar', () => {
  it('KEV off renders the muted dash, on renders the tag', () => {
    expect(mount(KevTag, { props: { on: false } }).text()).toBe('-')
    expect(mount(KevTag, { props: { on: true } }).text()).toBe('KEV')
  })

  it('EPSS renders the raw server probability as a percent; null (trivy) is a dash', () => {
    const w = mount(EpssBar, { props: { v: 0.734 } })
    expect(w.text()).toContain('73%')
    expect(w.find('.epss-bar i').attributes('data-heat')).toBe('hot')
    expect(mount(EpssBar, { props: { v: null } }).text()).toBe('-')
  })
})

describe('SlaCell', () => {
  it('overdue wins; otherwise renders server due_at as days-remaining (display only, B-5)', () => {
    expect(mount(SlaCell, { props: { dueAt: null, overdue: true } }).text()).toBe('overdue')
    const in5d = new Date(Date.now() + 5 * 86_400_000).toISOString()
    expect(mount(SlaCell, { props: { dueAt: in5d, overdue: false } }).text()).toBe('5d')
    expect(mount(SlaCell, { props: { dueAt: null, overdue: false } }).text()).toBe('-')
  })
})

describe('DisagreementBadge', () => {
  it('flags without reconciling — a ± marker with a help tooltip', () => {
    const w = mount(DisagreementBadge, { props: { title: 'trivy: high · grype: critical' } })
    expect(w.text()).toContain('±')
    expect(w.attributes('title')).toBe('trivy: high · grype: critical')
  })
})

describe('CountDisagree', () => {
  const marks = (w: ReturnType<typeof mount>) =>
    w.findAll('.cd-mark').map((m) => m.attributes('data-scanner'))

  it('disagreement keeps each count under its own scanner, never summed', () => {
    const w = mount(CountDisagree, { props: { trivy: 1234, grype: 1200, total: 1234 } })
    expect(marks(w)).toEqual(['trivy', 'grype'])
    expect(w.text()).toContain('1,234')
    expect(w.text()).toContain('1,200')
    expect(w.text()).toContain('Δ +34')
    expect(w.attributes('title')).toBe('Trivy found 1,234, Grype found 1,200. Trivy found 34 more.')
  })

  it('the hover names whichever scanner found more', () => {
    const w = mount(CountDisagree, { props: { trivy: 41, grype: 57, total: 57 } })
    expect(w.text()).toContain('Δ -16')
    expect(w.attributes('title')).toBe('Trivy found 41, Grype found 57. Grype found 16 more.')
  })

  it('agreement wears both marks over the one shared count', () => {
    const w = mount(CountDisagree, { props: { trivy: 55, grype: 55, total: 55 } })
    expect(marks(w)).toEqual(['trivy', 'grype'])
    expect(w.text()).toBe('TG55')
    expect(w.attributes('title')).toBe('Trivy and Grype report the same number: 55.')
  })

  /** The defect this replaced: one scanner counting alone rendered exactly like two agreeing. */
  it('a lone scanner is not dressed as agreement', () => {
    const w = mount(CountDisagree, { props: { total: 55, scanners: ['grype'] } })
    expect(marks(w)).toEqual(['grype'])
    expect(w.attributes('title')).toBe('Only Grype scanned this digest. It reports 55 findings.')
    const agreed = mount(CountDisagree, { props: { trivy: 55, grype: 55, total: 55 } })
    expect(w.text()).not.toBe(agreed.text())
  })

  it('a pair outranks a stale scanner list', () => {
    const w = mount(CountDisagree, { props: { trivy: 55, grype: 55, total: 55, scanners: ['grype'] } })
    expect(marks(w)).toEqual(['trivy', 'grype'])
  })

  it('falls back to the bare count only when nothing can attribute it', () => {
    const w = mount(CountDisagree, { props: { total: 55, scanners: [] } })
    expect(marks(w)).toEqual([])
    expect(w.text()).toBe('55')
  })
})

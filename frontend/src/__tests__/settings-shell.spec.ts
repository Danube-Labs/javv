/**
 * M9e slice 1 — the pure settings logic: the SLA form contract guards (parse/build/dirt) and
 * the §13 section registry's invariants. Panel rendering is the browser smoke's job.
 */
import { describe, expect, it } from 'vitest'

import type { SlaPolicy } from '@/api/generated'
import { SETTINGS_SECTIONS } from '@/views/settings/sections'
import {
  addChip,
  cloneScope,
  emptyScope,
  removeChip,
  scopeDirty,
} from '@/views/settings/scopeForm'
import { mintExpiry, tokenStatus, type TokenRow } from '@/views/settings/tokensForm'
import {
  draftFromPolicy,
  isDirty,
  parseWindow,
  policyFromDraft,
  SLA_KEYS,
} from '@/views/settings/slaForm'

const POLICY: SlaPolicy = {
  critical_days: 2,
  high_days: 7,
  medium_days: 30,
  low_days: 90,
  kev_days: 1,
}

describe('slaForm', () => {
  it('round-trips a policy through the draft', () => {
    expect(policyFromDraft(draftFromPolicy(POLICY))).toEqual(POLICY)
  })

  it('parseWindow: positive finite numbers only (the backend gt=0 guard)', () => {
    expect(parseWindow('7')).toBe(7)
    expect(parseWindow(' 0.5 ')).toBe(0.5) // fractional days are legal (12h KEV window)
    for (const bad of ['', '0', '-3', 'abc', '1e999', 'Infinity', 'NaN', '7d']) {
      expect.soft(parseWindow(bad), bad).toBeNull()
    }
  })

  it('policyFromDraft is all-or-nothing — one invalid window kills the PUT body', () => {
    const draft = draftFromPolicy(POLICY)
    draft.medium_days = '0'
    expect(policyFromDraft(draft)).toBeNull()
  })

  it('dirt is semantic: reformatting is clean, value changes and invalid edits are dirty', () => {
    const draft = draftFromPolicy(POLICY)
    expect(isDirty(draft, POLICY)).toBe(false)
    draft.high_days = '7.0' // same value, different spelling
    expect(isDirty(draft, POLICY)).toBe(false)
    draft.high_days = '14'
    expect(isDirty(draft, POLICY)).toBe(true)
    draft.high_days = 'x' // invalid edit must read dirty (and invalid), never silently clean
    expect(isDirty(draft, POLICY)).toBe(true)
  })

  it('draft covers exactly the SlaPolicy settings', () => {
    expect(Object.keys(draftFromPolicy(POLICY)).sort()).toEqual([...SLA_KEYS].sort())
  })
})

describe('tokensForm', () => {
  const row = (over: Partial<TokenRow>): TokenRow => ({
    id: 't1',
    cluster_id: 'c1',
    scanner: 'trivy',
    scope: 'push:findings',
    created_by: 'admin',
    created_at: '2026-07-01T00:00:00+00:00',
    expiry: null,
    disabled: false,
    last_ingest_at: null,
    ...over,
  })
  const NOW = new Date('2026-07-15T12:00:00Z')

  it('status: revoked wins over expiry; a past expiry reads expired; else active', () => {
    expect(tokenStatus(row({}), NOW)).toBe('active')
    expect(tokenStatus(row({ expiry: '2026-07-01T00:00:00+00:00' }), NOW)).toBe('expired')
    expect(tokenStatus(row({ expiry: '2026-08-01T00:00:00+00:00' }), NOW)).toBe('active')
    expect(tokenStatus(row({ disabled: true, expiry: '2026-07-01T00:00:00+00:00' }), NOW)).toBe('revoked')
  })

  it('mint expiry: both-empty omits; half-filled/garbage/past are INVALID, never silent', () => {
    expect(mintExpiry({ date: '', time: '' }, NOW)).toEqual({ kind: 'omit' })
    expect(mintExpiry({ date: '2026-08-01', time: '' }, NOW).kind).toBe('invalid') // half-filled
    expect(mintExpiry({ date: '', time: '12:00' }, NOW).kind).toBe('invalid')
    expect(mintExpiry({ date: '2026-08-01', time: '25:99' }, NOW).kind).toBe('invalid')
    expect(mintExpiry({ date: '2026-07-01', time: '00:00' }, NOW).kind).toBe('invalid') // past
    expect(mintExpiry({ date: '2026-08-01', time: '00:30' }, NOW)).toEqual({
      kind: 'iso',
      iso: new Date('2026-08-01T00:30').toISOString(),
    })
  })
})

describe('scopeForm', () => {
  it('addChip trims, drops empties and dedupes; removeChip filters', () => {
    expect(addChip([], '  prod ')).toEqual(['prod'])
    expect(addChip(['prod'], 'prod')).toEqual(['prod'])
    expect(addChip(['prod'], '   ')).toEqual(['prod'])
    expect(removeChip(['a', 'b'], 'a')).toEqual(['b'])
  })

  it('dirt is order-aware list inequality across the four FR-24 lists', () => {
    const saved = emptyScope()
    const draft = cloneScope(saved)
    expect(scopeDirty(draft, saved)).toBe(false)
    draft.ignore_kinds = ['Job']
    expect(scopeDirty(draft, saved)).toBe(true)
  })

  it('cloneScope detaches every list (a chip edit never mutates the saved copy)', () => {
    const saved = { ...emptyScope(), include_namespaces: ['prod'] }
    const draft = cloneScope(saved)
    draft.include_namespaces.push('dev')
    expect(saved.include_namespaces).toEqual(['prod'])
  })
})

describe('settings section registry (§13)', () => {
  it('keys are unique route segments', () => {
    const keys = SETTINGS_SECTIONS.map((s) => s.key)
    expect(new Set(keys).size).toBe(keys.length)
  })

  it('every section carries a real capability gate (A-4 bundles use these names)', () => {
    const known = new Set([
      'can_manage_settings',
      'can_manage_tokens',
      'can_manage_users',
      'can_manage_retention',
    ])
    for (const s of SETTINGS_SECTIONS) expect.soft(known.has(s.capability), s.key).toBe(true)
  })

  it('AI agents (MCP) is an organization section for the token admins (issue 1096)', () => {
    expect(SETTINGS_SECTIONS.find((s) => s.key === 'ai-agents')).toEqual({
      key: 'ai-agents',
      label: 'AI agents (MCP)',
      icon: 'cpu',
      scope: 'org',
      capability: 'can_manage_tokens',
    })
  })
})

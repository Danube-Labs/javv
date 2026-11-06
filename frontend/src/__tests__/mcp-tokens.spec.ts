/**
 * The AI agents (MCP) section of Settings (issue 1096 step 4, SCREENS §13.9): the window guards
 * mirror the backend's rules, and the section lists, makes, rotates and revokes MCP tokens.
 */
import { describe, expect, it } from 'vitest'

import {
  defaultExpiryDay,
  endpointUrl,
  expiryIso,
  expiryRange,
  levelLabel,
  MCP_LEVELS,
  MCP_NAME,
} from '@/views/settings/mcpTokensForm'
import { tokenStatus } from '@/views/settings/tokensForm'

// 2026-11-06 22:30 UTC: late in the UTC day, so a local-calendar slip would show
const NOW = Date.parse('2026-11-06T22:30:00Z')

describe('expiryRange', () => {
  it('starts tomorrow in UTC and ends on the UTC day of now + 90 days', () => {
    expect(expiryRange(NOW)).toEqual({ first: '2026-11-07', last: '2027-02-04' })
  })

  it('never ends after the backend cap: 00:00 UTC of the last day is within 90 days', () => {
    for (const ms of [NOW, Date.parse('2026-11-06T00:00:00Z'), Date.parse('2026-11-06T23:59:59Z')]) {
      const last = Date.parse(`${expiryRange(ms).last}T00:00:00Z`)
      expect(last - ms).toBeLessThanOrEqual(90 * 86_400_000)
    }
  })
})

describe('expiryIso', () => {
  it('gives 00:00 UTC of a day in the range', () => {
    expect(expiryIso('2026-11-07', NOW)).toBe('2026-11-07T00:00:00.000Z')
    expect(expiryIso('2027-02-04', NOW)).toBe('2027-02-04T00:00:00.000Z')
  })

  it('refuses today, a past day and a day after the last', () => {
    expect(expiryIso('2026-11-06', NOW)).toBeNull()
    expect(expiryIso('2026-01-01', NOW)).toBeNull()
    expect(expiryIso('2027-02-05', NOW)).toBeNull()
  })

  it('refuses an empty or malformed day', () => {
    for (const bad of ['', '2026-11', '2026-13-40', 'tomorrow']) expect(expiryIso(bad, NOW)).toBeNull()
  })

  it('accepts the day the window puts in the box', () => {
    expect(defaultExpiryDay(NOW)).toBe('2026-12-06')
    expect(expiryIso(defaultExpiryDay(NOW), NOW)).not.toBeNull()
  })
})

describe('MCP_NAME', () => {
  it('takes 3 to 64 lower-case letters, digits, dots, underscores or hyphens', () => {
    expect(['cursor', 'ci.agent_2', 'a-b', 'x'.repeat(64)].filter((n) => !MCP_NAME.test(n))).toEqual([])
    expect(['ab', 'Cursor', 'my agent', 'x'.repeat(65), 'mcp:x'].filter((n) => MCP_NAME.test(n))).toEqual([])
  })
})

describe('levels', () => {
  it('offers the three levels of the backend, in order', () => {
    expect(MCP_LEVELS.map((l) => l.value)).toEqual(['read', 'write', 'write_risk_accept'])
    expect(levelLabel('write_risk_accept')).toBe('Write and risk accept')
    expect(levelLabel('later')).toBe('later')
  })
})

describe('endpointUrl', () => {
  it('is the address of the page plus the path of the endpoint', () => {
    expect(endpointUrl('https://javv.example.org')).toBe('https://javv.example.org/api/v1/mcp')
    expect(endpointUrl('http://localhost:5173/')).toBe('http://localhost:5173/api/v1/mcp')
  })
})

describe('the status of an MCP token', () => {
  const row = { disabled: false, expiry: '2026-12-01T00:00:00Z' }
  it('is the rule of the scanner tokens: revoked, then expired, then active', () => {
    expect(tokenStatus(row, new Date(NOW))).toBe('active')
    expect(tokenStatus({ ...row, expiry: '2026-11-01T00:00:00Z' }, new Date(NOW))).toBe('expired')
    expect(tokenStatus({ ...row, disabled: true }, new Date(NOW))).toBe('revoked')
  })
})

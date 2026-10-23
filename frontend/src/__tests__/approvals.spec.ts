/**
 * Approvals view-model pins (M9d slice 4): expiry status derives from the DISPLAY clock
 * (never stored — expiry itself is immutable, D39); the warn window is the documented setting's
 * default; scope/scanner labels compact the D22 subject accurately.
 */
import { describe, expect, it } from 'vitest'

import { APPROVAL_FIELDS } from '@/approvals/fields.config'
import {
  EXPIRY_WARN_DAYS,
  daysUntil,
  expiryStatus,
  firstExpiryDate,
  findingsRoute,
  scannerLabel,
  scopeLabel,
} from '@/approvals/viewModel'

const NOW = new Date('2026-07-13T12:00:00Z').getTime()
const days = (n: number) => new Date(NOW + n * 86_400_000).toISOString()

describe('expiryStatus (the chip contract)', () => {
  it('derives all four states from the display clock', () => {
    expect(expiryStatus(null, NOW)).toBe('open-ended')
    expect(expiryStatus(days(30), NOW)).toBe('active')
    expect(expiryStatus(days(3), NOW)).toBe('expiring')
    expect(expiryStatus(days(-1), NOW)).toBe('expired')
  })

  it('the warn window boundary: exactly warnDays out is expiring; a breath past is active', () => {
    expect(expiryStatus(days(EXPIRY_WARN_DAYS), NOW)).toBe('expiring')
    expect(expiryStatus(new Date(NOW + (EXPIRY_WARN_DAYS * 86_400_000 + 1000)).toISOString(), NOW)).toBe('active')
  })

  it('expiry AT the clock instant is expired (the acceptance no longer stands)', () => {
    expect(expiryStatus(new Date(NOW).toISOString(), NOW)).toBe('expired')
  })

  it('unparseable expiry degrades to open-ended, never a crash', () => {
    expect(expiryStatus('not-a-date', NOW)).toBe('open-ended')
  })

  it('the setting default is 7 days (docs/CONFIGURATION.md)', () => {
    expect(EXPIRY_WARN_DAYS).toBe(7)
  })

  it('daysUntil ceils — tomorrow morning is 1d, not 0d', () => {
    expect(daysUntil(days(0.5), NOW)).toBe(1)
    expect(daysUntil(days(3), NOW)).toBe(3)
  })
})

describe('scope + scanner labels', () => {
  it('empty scope is cluster-wide; ns/img compact with +N', () => {
    expect(scopeLabel({ namespaces: [], images: [] })).toBe('cluster-wide')
    expect(scopeLabel({ namespaces: ['prod'], images: [] })).toBe('ns: prod')
    expect(scopeLabel({ namespaces: ['prod', 'stage'], images: ['nginx'] })).toBe(
      'ns: prod +1 · img: nginx',
    )
  })

  it('apply_both wins over a stray scanner value (D22)', () => {
    expect(scannerLabel({ apply_both_scanners: true, scanner: 'trivy' })).toBe('both')
    expect(scannerLabel({ apply_both_scanners: false, scanner: 'grype' })).toBe('grype')
    expect(scannerLabel({ apply_both_scanners: false, scanner: null })).toBe('both')
  })
})

describe('findingsRoute (where a decision row leads)', () => {
  const scope = (images: string[]) => ({ namespaces: [], images })

  it('searches the CVE', () => {
    expect(findingsRoute({ cve_id: 'CVE-2024-1', scope: scope([]) })).toEqual({
      name: 'findings',
      query: { q: 'CVE-2024-1' },
    })
  })

  it('narrows to the image when the scope names exactly one', () => {
    expect(findingsRoute({ cve_id: 'CVE-2024-1', scope: scope(['nginx']) }).query).toEqual({
      q: 'CVE-2024-1',
      image: 'nginx',
    })
  })

  it('does not narrow when the scope names several images', () => {
    expect(findingsRoute({ cve_id: 'CVE-2024-1', scope: scope(['nginx', 'redis']) }).query).toEqual({ q: 'CVE-2024-1' })
  })
})

describe('APPROVAL_FIELDS (issue 952)', () => {
  it('Status and Approver take several values; Scanner and the CVE search take one', () => {
    const multi = Object.fromEntries(APPROVAL_FIELDS.map((f) => [f.key, 'multi' in f && f.multi === true]))
    expect(multi).toEqual({ q: false, status: true, scanner: false, approver: true })
  })
})

describe('firstExpiryDate (issue 984)', () => {
  it('is tomorrow in UTC: a date stops at 00:00 UTC, so today is already over', () => {
    expect(firstExpiryDate(NOW)).toBe('2026-07-14')
  })

  it('reads the UTC calendar, not the local one, near midnight', () => {
    // 23:30 UTC on 13 July is already 14 July east of UTC; the server still counts the 13th
    expect(firstExpiryDate(new Date('2026-07-13T23:30:00Z').getTime())).toBe('2026-07-14')
    // 00:30 UTC on 14 July is still 13 July west of UTC; the 14th is over for the server
    expect(firstExpiryDate(new Date('2026-07-14T00:30:00Z').getTime())).toBe('2026-07-15')
  })

  it('agrees with expiryStatus: the date before it is expired at that moment', () => {
    const at = new Date('2026-07-14T00:30:00Z').getTime()
    expect(expiryStatus('2026-07-14', at)).toBe('expired')
    expect(expiryStatus(firstExpiryDate(at), at)).not.toBe('expired')
  })
})

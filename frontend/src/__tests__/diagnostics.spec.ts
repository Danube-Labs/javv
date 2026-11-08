/**
 * The About page's pure pieces (issue 341): the plain-text block "Copy diagnostics" puts on the
 * clipboard, the status → copy mapping for a failed read (audit rule 1: a busy backend never
 * reads as an outage), and the 24-hour UTC stamp they share.
 */
import { describe, expect, it } from 'vitest'

import { buildDiagnostics, formatUtc, readFailureCopy, type RunningMeta } from '@/about/diagnostics'

const META: RunningMeta = {
  version: '0.6.0',
  mapping_version: 18,
  envelope_versions: [3, 4],
  opensearch_version: '3.8.0',
  python_version: '3.12.13',
}

const NOW = new Date('2026-09-29T19:05:00Z')

describe('formatUtc', () => {
  it('is 24-hour UTC, never AM/PM or local time', () => {
    expect(formatUtc(new Date('2026-09-29T19:05:42Z'))).toBe('2026-09-29 19:05 UTC')
    expect(formatUtc(new Date('2026-01-02T03:04:00Z'))).toBe('2026-01-02 03:04 UTC')
  })
})

describe('buildDiagnostics', () => {
  it('lists every version on the page, the cluster, the browser and the time', () => {
    const text = buildDiagnostics({
      meta: META,
      frontendVersion: '0.6.0',
      cluster: { id: 'c-prod-eu-1', name: 'prod-eu' },
      scanners: [
        {
          scanner: 'trivy',
          scanner_version: '0.74.0',
          scanner_db_version: '2',
          scanner_db_built: '2026-09-29T12:00:00Z',
        },
        { scanner: 'grype', scanner_version: '0.119.0', scanner_db_version: null, scanner_db_built: null },
      ],
      userAgent: 'Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0',
      now: NOW,
    })
    expect(text.split('\n')).toEqual([
      'JAVV diagnostics · 2026-09-29 19:05 UTC',
      'JAVV release (backend): 0.6.0',
      'Frontend build: 0.6.0',
      'Store schema: v18',
      'Scanner report formats accepted: v3, v4',
      'OpenSearch: 3.8.0',
      'Python: 3.12.13',
      'Cluster: prod-eu (c-prod-eu-1)',
      'trivy: 0.74.0 · vulnerability database 2, built 2026-09-29 12:00 UTC',
      'grype: 0.119.0 · vulnerability database unknown, built unknown',
      'Browser: Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0',
    ])
  })

  it('says unavailable instead of dropping a line or inventing a value', () => {
    const text = buildDiagnostics({
      meta: null,
      frontendVersion: '0.6.0',
      cluster: null,
      scanners: [],
      userAgent: 'ua',
      now: NOW,
    })
    expect(text).toContain('JAVV release (backend): unavailable')
    expect(text).toContain('OpenSearch: unavailable')
    expect(text).toContain('Cluster: none selected')
    expect(text).toContain('Scanners: no committed run')
    expect(text).toContain('Frontend build: 0.6.0') // known locally, so never lost with the read
  })

  it('marks an unreachable store on its own line while the rest still reads', () => {
    const text = buildDiagnostics({
      meta: { ...META, opensearch_version: null },
      frontendVersion: '0.6.0',
      cluster: null,
      scanners: [],
      userAgent: 'ua',
      now: NOW,
    })
    expect(text).toContain('OpenSearch: unavailable')
    expect(text).toContain('JAVV release (backend): 0.6.0')
  })
})

describe('readFailureCopy', () => {
  it('names the cause: busy, down, or refused', () => {
    expect(readFailureCopy(429)).toMatch(/busy/)
    expect(readFailureCopy(503)).toMatch(/didn't answer/)
    expect(readFailureCopy(500)).toMatch(/didn't answer/)
    expect(readFailureCopy(undefined)).toMatch(/didn't answer/) // no response at all
    expect(readFailureCopy(403)).toMatch(/refused.*403/)
  })
})

/**
 * The N10 contract for the detail screen: per-scanner rows are ordered and compared but NEVER
 * merged; KEV/EPSS surface with their source scanner; image count pairs stay side-by-side with
 * zero-vs-nonzero flagged at disagreement grade. Null-tolerant for historical rows.
 */
import { describe, expect, it } from 'vitest'

import {
  affectedComponentRows,
  epssOf,
  kevOn,
  orderEvidence,
  primaryRow,
  scopeToPackage,
  severityDisagrees,
} from '@/findings/detailViewModel'
import type { FindingRow } from '@/stores/findings'

function row(over: Partial<FindingRow>): FindingRow {
  return {
    finding_key: 'k',
    cve_id: 'CVE-2024-0001',
    scanner: 'trivy',
    severity: 'HIGH',
    severity_canonical: 'high',
    image_repo: 'nginx',
    tag: '1.25',
    package_name: 'openssl',
    installed_version: '3.0.1',
    fixed_version: null,
    fixable: false,
    epss: null,
    kev: false,
    ptype: null,
    state: 'open',
    overdue: false,
    due_at: null,
    ...over,
  }
}

describe('detail view-model (per-scanner sacred)', () => {
  it('orders evidence trivy-first and keeps both rows verbatim — never merges', () => {
    const grype = row({ scanner: 'grype', severity: 'Critical', severity_canonical: 'critical' })
    const trivy = row({ scanner: 'trivy', severity: 'HIGH', severity_canonical: 'high' })
    const out = orderEvidence([grype, trivy])
    expect(out.map((r) => r.scanner)).toEqual(['trivy', 'grype'])
    expect(out[0]!.severity).toBe('HIGH') // verbatim, not reconciled
    expect(out[1]!.severity).toBe('Critical')
    expect(out).toHaveLength(2)
  })

  it('flags severity disagreement from the canonical pair or the precomputed flag', () => {
    const agree = [row({}), row({ scanner: 'grype' })]
    expect(severityDisagrees(agree)).toBe(false)
    const differ = [row({}), row({ scanner: 'grype', severity_canonical: 'critical' })]
    expect(severityDisagrees(differ)).toBe(true)
    const flagged = [row({ disagree: true }), row({ scanner: 'grype', disagree: true })]
    expect(severityDisagrees(flagged)).toBe(true)
  })

  it('primary row honors the clicked scanner and falls back to scanner order', () => {
    const rows = [row({}), row({ scanner: 'grype' })]
    expect(primaryRow(rows, 'grype')?.scanner).toBe('grype')
    expect(primaryRow(rows, 'unknown-scanner')?.scanner).toBe('trivy')
    expect(primaryRow([], 'trivy')).toBeNull()
  })

  it('KEV/EPSS come from whichever row attests them — null-tolerant (historical rows)', () => {
    const historical = [
      row({ kev: null as unknown as boolean, epss: null }),
      row({ scanner: 'grype', kev: null as unknown as boolean, epss: null }),
    ]
    expect(kevOn(historical)).toBe(false)
    expect(epssOf(historical)).toBeNull()

    const enriched = [row({}), row({ scanner: 'grype', kev: true, epss: 0.53 })]
    expect(kevOn(enriched)).toBe(true)
    expect(epssOf(enriched)).toEqual({ value: 0.53, scanner: 'grype' })
  })

  it('scopes evidence to one package — the clicked one, or the first row on deep links', () => {
    const rows = [
      row({ finding_key: 'a', package_name: 'libcurl4', scanner: 'trivy' }),
      row({ finding_key: 'b', package_name: 'curl', scanner: 'trivy' }),
      row({ finding_key: 'c', package_name: 'libcurl4', scanner: 'grype' }),
      row({ finding_key: 'd', package_name: 'curl', scanner: 'grype' }),
    ]
    const clicked = scopeToPackage(rows, 'curl', '3.0.1')
    expect(clicked.scoped.map((r) => r.finding_key)).toEqual(['b', 'd'])
    expect(clicked.otherPackages).toEqual(['libcurl4'])

    const deepLink = scopeToPackage(rows, null)
    expect(deepLink.scoped.map((r) => r.package_name)).toEqual(['libcurl4', 'libcurl4'])
    expect(scopeToPackage([], 'curl').scoped).toEqual([])
  })

  it('affected components collapse agreeing scanners into one row, never their versions', () => {
    const rows = affectedComponentRows([
      row({ image_repo: 'nginx', tag: '1.23', package_name: 'curl', installed_version: '7.74.0', fixed_version: null, scanner: 'trivy', namespaces: ['prod'] }),
      row({ image_repo: 'nginx', tag: '1.23', package_name: 'curl', installed_version: '7.74.0', fixed_version: null, scanner: 'grype', namespaces: ['prod', 'staging'] }),
      // same package, DIFFERENT fixed version per scanner — must split, never merge (per-scanner sacred)
      row({ image_repo: 'redis', tag: null, package_name: 'zlib', installed_version: '1.2', fixed_version: '1.3', scanner: 'trivy', namespaces: ['cache'] }),
      row({ image_repo: 'redis', tag: null, package_name: 'zlib', installed_version: '1.2', fixed_version: '1.4', scanner: 'grype', namespaces: ['cache'] }),
      // single-scanner image — the silent scanner is visible by absence from the tags
      row({ image_repo: 'alpine', tag: '3.19', package_name: 'busybox', installed_version: '1.36', fixed_version: null, scanner: 'grype', namespaces: [] }),
    ])
    expect(rows.map((r) => `${r.image}·${r.packageName}·${r.fixed ?? '-'}`)).toEqual([
      'alpine:3.19·busybox·-',
      'nginx:1.23·curl·-',
      'redis·zlib·1.3',
      'redis·zlib·1.4',
    ])
    // agreeing scanners collapse into tags; namespaces are the union, per row
    expect(rows[1]).toMatchObject({ scanners: ['trivy', 'grype'], namespaces: ['prod', 'staging'] })
    // the version split keeps one scanner per row — disagreement stays visible
    expect(rows[2]!.scanners).toEqual(['trivy'])
    expect(rows[3]!.scanners).toEqual(['grype'])
    expect(rows[4]).toBeUndefined()
  })

  it('the paths stay one entry for each finding of a row, by scanner and digest, never joined (issue 1077)', () => {
    const [r] = affectedComponentRows([
      // raw server rows: grype first, two digests of one tag, trivy with no path at all
      row({ scanner: 'grype', image_digest: 'sha256:bbb', locations: ['/var/lib/dpkg/status'], locations_total: 1 }),
      row({ scanner: 'trivy', image_digest: 'sha256:bbb', locations: [], locations_total: 0 }),
      row({ scanner: 'grype', image_digest: 'sha256:aaa', locations: ['/a', '/b'], locations_total: 70 }),
      // a scan before schema 5: no field at all, which is not the same as 0
      row({ scanner: 'trivy', image_digest: 'sha256:aaa' }),
    ])
    expect(r!.scanners).toEqual(['trivy', 'grype'])
    expect(r!.paths).toEqual([
      { scanner: 'trivy', digest: 'sha256:aaa', total: null, paths: [] },
      { scanner: 'trivy', digest: 'sha256:bbb', total: 0, paths: [] },
      { scanner: 'grype', digest: 'sha256:aaa', total: 70, paths: ['/a', '/b'] },
      { scanner: 'grype', digest: 'sha256:bbb', total: 1, paths: ['/var/lib/dpkg/status'] },
    ])
  })
})

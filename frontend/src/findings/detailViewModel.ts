/**
 * Pure view-model for the finding detail screen (M9b slice 2). Per-scanner is sacred: nothing
 * here merges, reconciles, or sums across scanners — it only orders rows, compares them, and
 * flags disagreement. KEV/EPSS are grype-only enrichments (INDEX-MAP), so the header surfaces
 * them from whichever row carries them, labeled with the source scanner. Historical (`as_of`)
 * rows null-out unattested fields — every function tolerates nulls.
 */
import { type FindingPaths, pathsOf } from '@/findings/paths'
import type { FindingRow } from '@/stores/findings'

export const SCANNER_ORDER = ['trivy', 'grype'] as const

/**
 * The read of a finding asks for the package of the link, and its rows are one for each scanner
 * (finding identity includes the package). The evidence compares like with like: one package
 * and version. A link that names a package scopes to that package only, never to another one:
 * the first row of another package once took the head band and the Triage cell (issue 1227).
 * A link with no package (an old deep link) scopes to the first row's package.
 */
export function scopeToPackage(rows: FindingRow[], pkg?: string | null, ver?: string | null): FindingRow[] {
  const ordered = orderEvidence(rows)
  const anchor = pkg
    ? ordered.find((r) => r.package_name === pkg && (!ver || r.installed_version === ver))
    : ordered[0]
  if (!anchor) return []
  return ordered.filter(
    (r) => r.package_name === anchor.package_name && r.installed_version === anchor.installed_version,
  )
}

export interface PackageOnImage {
  name: string
  version: string | null
  /** the scanners that found this package and version, in SCANNER_ORDER */
  scanners: string[]
}

/** Each package and version of the CVE on the image, for the package menu of the head band. */
export function packagesOnImage(rows: FindingRow[]): PackageOnImage[] {
  const byKey = new Map<string, PackageOnImage>()
  for (const r of rows) {
    const version = r.installed_version ?? null
    const key = `${r.package_name}\u0000${version ?? ''}`
    const p = byKey.get(key) ?? { name: r.package_name, version, scanners: [] }
    if (!p.scanners.includes(r.scanner)) p.scanners.push(r.scanner)
    byKey.set(key, p)
  }
  return [...byKey.values()]
    .map((p) => ({ ...p, scanners: [...p.scanners].sort((a, b) => scannerRank(a) - scannerRank(b)) }))
    .sort((a, b) => a.name.localeCompare(b.name) || (a.version ?? '').localeCompare(b.version ?? '', undefined, { numeric: true }))
}

/** Evidence rows in fixed scanner order — verbatim rows, never merged. */
export function orderEvidence(rows: FindingRow[]): FindingRow[] {
  return [...rows].sort((a, b) => scannerRank(a.scanner) - scannerRank(b.scanner))
}

function scannerRank(s: string): number {
  const i = (SCANNER_ORDER as readonly string[]).indexOf(s)
  return i === -1 ? SCANNER_ORDER.length : i
}

/** True when the pair disagrees on canonical severity, or a row's precomputed flag says so. */
export function severityDisagrees(rows: FindingRow[]): boolean {
  if (rows.some((r) => r.disagree === true)) return true
  const canon = new Set(rows.map((r) => r.severity_canonical).filter(Boolean))
  return canon.size > 1
}

/** The header's primary row: the scanner the user clicked, else first in scanner order. */
export function primaryRow(rows: FindingRow[], preferredScanner?: string | null): FindingRow | null {
  if (rows.length === 0) return null
  return rows.find((r) => r.scanner === preferredScanner) ?? orderEvidence(rows)[0]!
}

/** KEV across the pair (grype-only field; null on historical rows). */
export function kevOn(rows: FindingRow[]): boolean {
  return rows.some((r) => r.kev === true)
}

/** The EPSS score + which scanner attested it, or null when no row carries one. */
export function epssOf(rows: FindingRow[]): { value: number; scanner: string } | null {
  const row = orderEvidence(rows).find((r) => typeof r.epss === 'number')
  return row ? { value: row.epss as number, scanner: row.scanner } : null
}

/** One "affected components" row (prototype parity — the component is the package inside a
 * running image; workload names don't exist in the data, D30). Namespaces ride per row.
 * Scanners are LISTED, never merged: the group key includes both versions, so a scanner
 * disagreement on current/fixed splits into separate rows and stays visible. The paths stay
 * per finding (issue 1077): one entry for each scanner and digest in the row, never joined. */
export interface AffectedComponentRow {
  image: string
  packageName: string
  current: string | null
  fixed: string | null
  namespaces: string[]
  scanners: string[]
  paths: FindingPaths[]
}

export function affectedComponentRows(rows: FindingRow[]): AffectedComponentRow[] {
  const byKey = new Map<string, AffectedComponentRow>()
  for (const r of rows) {
    const image = `${r.image_repo}${r.tag ? ':' + r.tag : ''}`
    const key = [image, r.package_name, r.installed_version ?? '', r.fixed_version ?? ''].join('|')
    let out = byKey.get(key)
    if (!out) {
      out = {
        image,
        packageName: r.package_name,
        current: r.installed_version,
        fixed: r.fixed_version,
        namespaces: [],
        scanners: [],
        paths: [],
      }
      byKey.set(key, out)
    }
    const ns = Array.isArray(r.namespaces) ? (r.namespaces as string[]) : []
    for (const n of ns) if (!out.namespaces.includes(n)) out.namespaces.push(n)
    if (!out.scanners.includes(r.scanner)) out.scanners.push(r.scanner)
    out.paths.push(pathsOf(r))
  }
  const out = [...byKey.values()]
  const rank = (s: string) => (SCANNER_ORDER as readonly string[]).indexOf(s)
  for (const r of out) {
    r.namespaces.sort()
    r.scanners.sort((a, b) => rank(a) - rank(b))
    r.paths.sort((a, b) => rank(a.scanner) - rank(b.scanner) || (a.digest ?? '').localeCompare(b.digest ?? ''))
  }
  return out.sort(
    (a, b) =>
      a.image.localeCompare(b.image) ||
      a.packageName.localeCompare(b.packageName) ||
      (a.fixed ?? '').localeCompare(b.fixed ?? ''),
  )
}

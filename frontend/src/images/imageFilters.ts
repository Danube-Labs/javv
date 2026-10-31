/** Pure filter layer for the Running-images screen (unit-tested): the committed inventory is
 * one run's rows, fully served — matching + bucket counts derive from those rows (IMAGE
 * counts). Severity buckets use the canonical vocabulary mapped from the doc's short keys. */
import { FACET_CAP, type ValueSearch } from '@/filters/facets'
import type { Selections } from '@/filters/fields.config'
import type { FilterMode, Modes } from '@/stores/filters'
import type { ImageRow } from '@/stores/images'
import type { Severity } from '@/styles/tokens'

const SEV_OF_DOC: readonly [Severity, keyof ImageRow][] = [
  ['critical', 'crit'],
  ['high', 'high'],
  ['medium', 'med'],
  ['low', 'low'],
  ['negligible', 'negligible'],
  ['unknown', 'unknown'],
]

const sevCount = (row: ImageRow, sev: Severity): number => {
  const key = SEV_OF_DOC.find(([s]) => s === sev)![1]
  return (row[key] as number) ?? 0
}

/** The scanners with a committed scan of this digest: the doc's own cycle scanner PLUS the
 * D5b pair evidence — the pair only exists when the OTHER scanner has a committed scan, so
 * `scanners: [trivy]` with a grype_count means grype scanned it too (the doc's severity
 * buckets still belong to the committing scanner alone). */
export function scannersOf(row: ImageRow): string[] {
  const out = new Set(row.scanners)
  if (row.trivy_count != null) out.add('trivy')
  if (row.grype_count != null) out.add('grype')
  return [...out]
}

interface Bucket {
  key: string
  count: number
  by_scanner: Record<string, number>
}

/* The repo and tag lists stop at the server facet cap (the rail's "top 32 by count" note): a
 * fleet-sized run has one repo/tag per image, and an uncapped list would grow the rail without
 * bound. The menu's value search reaches the rest (searchImageValues, issue 1064). */

/** The values of each list field of an image row. */
const VALUES_OF: Record<string, (r: ImageRow) => readonly (string | null | undefined)[]> = {
  namespaces: (r) => r.namespaces,
  repos: (r) => [r.image_repo],
  tags: (r) => [r.tag],
}

/** Image counts of each value of one list field, largest first, with no cap. */
function countsOf(rows: ImageRow[], facetKey: string): Bucket[] {
  const values = VALUES_OF[facetKey]!
  const counts = new Map<string, number>()
  for (const r of rows) for (const v of values(r)) if (v) counts.set(v, (counts.get(v) ?? 0) + 1)
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({ key, count, by_scanner: {} }))
}

/** The values of one list field that contain a text, in any case, from all the rows and not
 * only the top 32: the browser holds the whole run, so it answers the menu itself (issue 1064). */
export function searchImageValues(rows: ImageRow[], facetKey: string, text: string): ValueSearch | null {
  if (!(facetKey in VALUES_OF)) return null
  const needle = text.toLowerCase()
  const hits = countsOf(rows, facetKey).filter((b) => b.key.toLowerCase().includes(needle))
  return { buckets: hits.slice(0, FACET_CAP), more: hits.length > FACET_CAP }
}

/** FacetsResponse-shaped buckets for the rail/bar — counts are images, not findings. */
export function imagesFacets(rows: ImageRow[]): Record<string, Bucket[]> {
  const bucket = (key: string, count: number): Bucket => ({ key, count, by_scanner: {} })
  const severity = SEV_OF_DOC.map(([sev]) =>
    bucket(sev, rows.filter((r) => sevCount(r, sev) > 0).length),
  ).filter((b) => b.count > 0)
  const scanners = ['trivy', 'grype'].map((s) =>
    bucket(s, rows.filter((r) => scannersOf(r).includes(s)).length),
  )
  return {
    severity,
    scanner: scanners,
    namespaces: countsOf(rows, 'namespaces'),
    repos: countsOf(rows, 'repos').slice(0, FACET_CAP),
    tags: countsOf(rows, 'tags').slice(0, FACET_CAP),
  }
}

/**
 * One field's verdict. Include keeps the rows that hit; exclude keeps the rows that don't —
 * the strict complement of the same predicate, so "severity is not critical" means an image
 * with ZERO critical findings, not an image with its criticals subtracted. A finding IS one
 * severity, but an image spans all of them, which is why this reading has to be stated:
 * the findings grid never has to answer it.
 *
 * Excluding a severity therefore returns very few rows, often none, and that is the correct
 * answer rather than a bug to fix: a typical cluster has criticals in nearly every image, so
 * the set with none of them is tiny. Ruled deliberately with the counts in hand. The header
 * always reads "N of M images", so a small N stays legible as a filtered result.
 */
const keep = (selected: readonly string[], mode: FilterMode, hit: boolean) =>
  selected.length === 0 || (mode === 'not' ? !hit : hit)

/** Selections → the matching inventory rows. Multi-value fields OR within, AND across. */
export function filterImages(rows: ImageRow[], sel: Selections, modes: Modes = {}): ImageRow[] {
  const q = (sel.q?.[0] ?? '').toLowerCase()
  const sevs = (sel.severity ?? []) as Severity[]
  const scanners = sel.scanner ?? []
  const attrs = sel.attr ?? []
  const namespaces = sel.namespace ?? []
  const repos = sel.repo ?? []
  const tags = sel.tag ?? []
  const modeOf = (key: string): FilterMode => modes[key] ?? 'is'
  return rows.filter((r) => {
    if (q && !`${r.image_repo} ${r.tag} ${r.namespaces.join(' ')}`.toLowerCase().includes(q))
      return false
    if (!keep(sevs, modeOf('severity'), sevs.some((s) => sevCount(r, s) > 0))) return false
    if (!keep(scanners, modeOf('scanner'), scanners.some((s) => scannersOf(r).includes(s))))
      return false
    if (attrs.includes('fixable') && !(r.fixable > 0)) return false
    if (!keep(namespaces, modeOf('namespace'), namespaces.some((ns) => r.namespaces.includes(ns))))
      return false
    // repo and tag are single-valued per row, so the hit is an exact match, not an overlap
    if (!keep(repos, modeOf('repo'), repos.includes(r.image_repo))) return false
    if (!keep(tags, modeOf('tag'), tags.includes(r.tag))) return false
    return true
  })
}

/** The filtered rows as CSV (the list export — inventory rows, already served).
 * String cells mirror the server's `sanitize_cell`: a leading `=` `+` `-` `@` TAB or CR
 * would arm as a spreadsheet formula (CSV injection — repo/tag/namespaces are untrusted
 * k8s/scanner input), so it's neutralized with a leading apostrophe. Non-strings can't
 * be formulas and serialize plainly (negative counts stay bare numbers). */
export function imagesCsv(rows: ImageRow[]): string {
  const esc = (v: unknown) => {
    let s = String(v ?? '')
    if (typeof v === 'string' && /^[=+\-@\t\r]/.test(s)) s = `'${s}`
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s
  }
  const header = [
    'image_repo', 'tag', 'image_digest', 'namespaces', 'scanners', 'critical', 'high', 'medium',
    'low', 'negligible', 'unknown', 'total', 'fixable', 'trivy_count', 'grype_count',
    'count_delta', 'replicas', 'last_seen',
  ]
  const line = (r: ImageRow) =>
    [
      r.image_repo, r.tag, r.image_digest, r.namespaces.join(' '), r.scanners.join(' '), r.crit,
      r.high, r.med, r.low, r.negligible, r.unknown, r.total, r.fixable, r.trivy_count ?? '',
      r.grype_count ?? '', r.count_delta ?? '', r.replicas, r['@timestamp'],
    ]
      .map(esc)
      .join(',')
  return [header.join(','), ...rows.map(line)].join('\n')
}

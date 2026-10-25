/**
 * Scanner-lens helpers shared by every faceted dashboard (Overview, All clusters — one copy,
 * was views/overviewLens.ts + views/fleetLens.ts): a bucket's display count under the lens is
 * the server's by_scanner split, never a client re-aggregation.
 */

export type ScannerLens = 'all' | 'trivy' | 'grype'

/** The scanner switch of a page that shows both scanners (Overview, All clusters, a dashboard). */
export const SCANNER_LENS_OPTS = [
  { value: 'all', label: 'All scanners' },
  { value: 'trivy', label: 'trivy', accent: 'var(--scanner-trivy-fg)' },
  { value: 'grype', label: 'grype', accent: 'var(--scanner-grype-fg)' },
] as const

/** The wire shape every facet bucket shares (stores/overview FacetBucket, structurally). */
export interface LensBucket {
  key: string
  count: number
  by_scanner: Record<string, number>
}

export function countOf(bucket: LensBucket | null | undefined, scanner: ScannerLens): number {
  if (!bucket) return 0
  return scanner === 'all' ? bucket.count : (bucket.by_scanner[scanner] ?? 0)
}

/** A named bucket out of a server facets map, read through the lens. */
export function facetCount(
  facets: Record<string, LensBucket[]>,
  facet: string,
  key: string,
  scanner: ScannerLens,
): number {
  return countOf(
    facets[facet]?.find((b) => b.key === key),
    scanner,
  )
}

export const fmt = (n: number) => n.toLocaleString('en-US')

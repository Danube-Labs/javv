/**
 * Shapes the M6 facets response for display. Both FacetRail and FilterBar list values through
 * `facetItems()`, so a field added to the config surfaces in both automatically (PLAN gate).
 *
 * Counts are passed through from the server verbatim — the per-scanner split is display data,
 * NEVER summed or otherwise combined client-side (FR-12, per-scanner sacred).
 */
import { valueLabel, type FilterField } from './fields.config'

export interface FacetBucket {
  key: string
  count: number
  by_scanner: Record<string, number>
}

export type FacetsResponse = Record<string, FacetBucket[]>

/** The most buckets one facet gives: backend `query/aggs._FACET_TERMS_SIZE`, a fixed size in
 * docs/CONFIGURATION.md ("Fixed aggregation sizes"). A list with fewer buckets is complete. */
export const FACET_CAP = 32

export interface FacetItem {
  value: string
  label: string
  /** Server-side count; null when the count is not known: the server did not count the field,
   * or it stopped at FACET_CAP buckets before this value. */
  count: number | null
  byScanner: Record<string, number> | null
  /** Config-declared hover explanation (flags only); wins over the scanner split. */
  hint?: string
}

const item = (value: string, label: string, bucket?: FacetBucket, hint?: string): FacetItem => ({
  value,
  label,
  count: bucket ? bucket.count : null,
  byScanner: bucket ? bucket.by_scanner : null,
  ...(hint !== undefined ? { hint } : {}),
})

/** The most buckets the server gives for one field: its own size, or FACET_CAP. */
export function capOf(field: FilterField): number {
  return field.type === 'terms' && field.facetCap !== undefined ? field.facetCap : FACET_CAP
}

/** The bucket of one value of a fixed list. A value with no bucket has 0 rows when the server
 * counted the field and gave fewer buckets than its cap (issue 980). Otherwise its count is
 * not known, so it gets no bucket. */
function countOf(
  buckets: FacetBucket[] | undefined,
  value: string,
  cap: number,
): FacetBucket | undefined {
  if (!buckets) return undefined
  const hit = buckets.find((b) => b.key === value)
  if (hit || buckets.length >= cap) return hit
  return { key: value, count: 0, by_scanner: {} }
}

/** Display items for one field, or null when the field has no listable values (text fields).
 * `selected` are the field's picked values: on a field with no fixed vocabulary, one the server's
 * buckets leave out still gets a row. A fixed vocabulary lists its own values only. */
export function facetItems(
  field: FilterField,
  facets: FacetsResponse,
  selected: readonly string[] = [],
): FacetItem[] | null {
  if (field.type === 'text') return null

  if (field.type === 'flags') {
    return field.values.map((flag) =>
      item(flag.key, flag.label, countOf(facets[flag.param], 'true', FACET_CAP), flag.hint),
    )
  }

  const buckets = field.facetKey ? (facets[field.facetKey] ?? []) : []
  if (field.values) {
    // static vocabulary: config order, counts filled in where the server aggregated
    const counted = field.facetKey ? facets[field.facetKey] : undefined
    return field.values.map((v) => item(v, valueLabel(field, v), countOf(counted, v, capOf(field))))
  }
  // dynamic vocabulary: the server's buckets, in server order. A picked value can be missing from
  // them: below the top 32, or (a facet that counts with its own filter) excluded. It is added
  // last, with no count, so it can still be seen and taken out (issue 949)
  const listed = new Set(buckets.map((b) => b.key))
  const extra = [...new Set(selected)]
    .filter((v) => !listed.has(v))
    .map((v) => item(v, valueLabel(field, v)))
  return [...buckets.map((b) => item(b.key, valueLabel(field, b.key), b)), ...extra]
}

/** `trivy 791 · grype 854` — tooltip text for the per-scanner split. */
export function scannerSplit(byScanner: Record<string, number> | null): string {
  if (!byScanner) return ''
  return Object.entries(byScanner)
    .map(([scanner, count]) => `${scanner} ${count}`)
    .join(' · ')
}

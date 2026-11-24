/**
 * The filters of a screen that the Scan ingest strip applies (issue 1293). A scan record holds the
 * namespaces, the image, the tag, the digest and the scanner of a scan, with the names of the
 * findings filters, so `GET /trends/scans` takes those filters. The other filters of a screen
 * (severity, state, KEV, the search and others) select findings, and the strip says that it does
 * not apply them.
 */

/** The query parameters of `GET /trends/scans` that filter the scans. */
export const SCAN_FILTER_PARAMS = [
  'namespace',
  'exclude_namespace',
  'image_repo',
  'exclude_image_repo',
  'tag',
  'exclude_tag',
  'untagged',
  'image_digest',
  'scanner',
  'exclude_scanner',
] as const

/** the route takes only these two (a Literal), and another value gets 422 */
const SCANNERS = new Set(['trivy', 'grype'])
/** parts of a query that are not filters: the tenant, the time, the window of "New in range",
 * and `present`, which a saved filter set holds on each panel */
const NOT_FILTERS = new Set(['cluster_id', 'as_of', 'window_days', 'present'])
const SCAN_PARAMS = new Set<string>(SCAN_FILTER_PARAMS)

const isSet = (value: unknown): boolean =>
  value !== null && value !== undefined && value !== false && value !== '' && !(Array.isArray(value) && value.length === 0)

export interface ScanFilters {
  /** the filters that the strip sends to `GET /trends/scans` */
  applied: Record<string, unknown>
  /** the parameters of the other filters that are on, in the order of the query */
  ignored: string[]
}

/** Split a filter query into the scan filters and the other filters that are on. */
export function scanFilters(query: Record<string, unknown>): ScanFilters {
  const applied: Record<string, unknown> = {}
  const ignored: string[] = []
  for (const [param, value] of Object.entries(query)) {
    if (NOT_FILTERS.has(param) || !isSet(value)) continue
    const scanner = param === 'scanner' || param === 'exclude_scanner'
    if (SCAN_PARAMS.has(param) && (!scanner || SCANNERS.has(String(value)))) applied[param] = value
    else ignored.push(param)
  }
  return { applied, ignored }
}

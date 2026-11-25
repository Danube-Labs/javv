/**
 * The togglable findings-grid columns — ONE list drives both the table's `v-if`s and the
 * Columns menu (same one-config-drives-both discipline as the filter module). Only
 * Vulnerability and Severity are fixed and not listed (the row's identity); everything
 * else — State included (operator 2026-07-11) — moves and toggles freely.
 */
export const FINDINGS_COLUMNS = [
  // the time lens (operator 2026-07-11): identity leads, time sits first after the pins —
  // sortable so "newest ingest wave first" is one header click, never the default sort
  ['first_seen', 'First seen'],
  ['last_scan', 'Last scan'],
  ['epss', 'EPSS'],
  ['kev', 'KEV'],
  ['package', 'Package'],
  // the number of paths of the finding; the row opens to list them (issue 1205)
  ['paths', 'Paths'],
  ['current', 'Current'],
  ['fixed', 'Fixed'],
  ['image', 'Image'],
  // the tag of the image, with its own +/- (issue 1317); while it shows, the Image cell drops it
  ['tag', 'Tag'],
  ['namespace', 'Namespace'],
  ['images', 'Affected images'],
  ['scanner', 'Scanner'],
  ['sla', 'SLA'],
  ['state', 'State'],
  ['assignee', 'Assignee'],
] as const

export type FindingsColumnKey = (typeof FINDINGS_COLUMNS)[number][0]

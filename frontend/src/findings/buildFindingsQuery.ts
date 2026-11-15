/**
 * Pure option-builder for the findings grid (bolt M9b DoD — the contract):
 *   - `cluster_id` ALWAYS (via the filter builder, which throws without one);
 *   - `present=true` on every query — "now" views never see reconciled-away rows (INDEX-MAP);
 *   - `as_of` passes through only when time-traveling (D28);
 *   - sort restricted to the server's whitelist — an unknown field is a bug here, not a 422 there;
 *   - cursor paging (PIT + search_after): `size` + optional `cursor`, NO offset — the shipped M6
 *     contract has no `from` (bolt README updated 2026-07-09);
 *   - `locations=true` only while the Paths column shows: the cursor does not keep it, so each
 *     page asks again.
 * Filter params come from the M9a `buildFilterQuery` — one builder, not two dialects.
 */
import { buildFilterQuery, type FilterGlobals, type FilterQuery } from '@/filters/buildFilterQuery'
import type { FilterField, Selections } from '@/filters/fields.config'
import type { Modes } from '@/stores/filters'

export const SORT_FIELDS = ['severity_rank', 'first_seen_at', 'last_scan_at', 'cvss', 'epss'] as const
export type SortField = (typeof SORT_FIELDS)[number]
export type SortOrder = 'asc' | 'desc'

export interface GridState {
  sort: SortField
  order: SortOrder
  size: number
  cursor?: string | null
  /** the grid shows the Paths column: each row then needs its paths (issue 1205) */
  locations?: boolean
}

export function buildFindingsQuery(
  fields: readonly FilterField[],
  selections: Selections,
  globals: FilterGlobals,
  grid: GridState,
  modes: Modes = {},
): FilterQuery {
  if (!SORT_FIELDS.includes(grid.sort)) {
    throw new Error(`buildFindingsQuery: sort must be one of ${SORT_FIELDS.join(', ')}`)
  }
  const query = buildFilterQuery(fields, selections, globals, modes)
  query.present = true
  query.sort = grid.sort
  query.order = grid.order
  query.size = grid.size
  if (grid.cursor) query.cursor = grid.cursor
  if (grid.locations) query.locations = true
  return query
}

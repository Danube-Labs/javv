/**
 * The filters of a dashboard panel (issue 999). A panel stores them in the shape of a saved
 * view's preset, so the saved-view helpers give their words and their Findings link.
 */
import type { PanelAuditFilters, ViewPreset } from '@/api/generated'
import { AUDIT_FIELDS, TRIAGE_ACTIONS, TRIAGE_ENTITY_TYPES } from '@/audit/fields.config'
import { daysFromWindow } from '@/contributors/viewModel'
import type { CatalogPanel } from '@/dashboards/catalog'
import { FINDINGS_FIELDS, type FilterField } from '@/filters/fields.config'
import { presetParts, presetToRouteQuery } from '@/findings/savedViews'

type Filters = ViewPreset | null | undefined
type AuditFilters = PanelAuditFilters | null | undefined

/** The filters a panel reads with. "New in range" counts in the range of the dashboard, as on
 * Findings, and not in the days stored when the filter was applied (operator, 2026-10-31). */
export function panelFiltersAt(filters: Filters, windowDays: number): ViewPreset | null {
  if (!filters) return null
  if (filters.new_within_days === null || filters.new_within_days === undefined) return filters
  return { ...filters, new_within_days: daysFromWindow(windowDays) }
}

/** The fields a panel's settings can filter on: the Findings fields less Scanner, which the
 * dashboard switch and the panel's own setting pick, and less the filters the panel refuses. */
export function panelFilterFields(panel: Pick<CatalogPanel, 'refusedFilters'>): readonly FilterField[] {
  const refused = panel.refusedFilters ?? []
  return FINDINGS_FIELDS.filter((f) => f.key !== 'scanner' && !(f.type !== 'flags' && refused.includes(f.param)))
}

/** The filters of a panel in words, one text for each. */
export function panelFilterParts(filters: Filters): string[] {
  return filters ? presetParts(FINDINGS_FIELDS, filters) : []
}

/** The facets read of a panel: the dashboard's query with the panel's filters. Each facet then
 * counts under all of them (`all_filters`, decision 4), so "Namespace is not kube-system" leaves
 * that row out of Findings by namespace. A panel with no filters sends the dashboard's query as
 * it is, so it shares one read with the other panels. */
export function panelQuery<Q extends { cluster_id: string; as_of?: string }>(
  base: Q,
  filters: Filters,
): Q & Record<string, unknown> {
  if (panelFilterParts(filters).length === 0) return base
  const params = Object.fromEntries(
    Object.entries(filters as Record<string, unknown>).filter(([, v]) => v !== null && v !== undefined),
  )
  return { ...params, ...base, all_filters: true }
}

/** The Findings link of a click in a panel: the panel's filters, then the clicked row's own
 * values. A row value takes the place of the panel's filter on the same field, so a click on the
 * critical band of a panel with "Severity is not low" opens the critical findings. The flags of
 * the panel and of the row both stay. */
export function panelFindingsQuery(filters: Filters, row: Record<string, string>): Record<string, string> {
  const query = filters ? presetToRouteQuery(FINDINGS_FIELDS, filters) : {}
  for (const [key, value] of Object.entries(row)) {
    if (key === 'attr' && query.attr) {
      query.attr = [...new Set([...query.attr.split(','), ...value.split(',')])].join(',')
    } else {
      query[key] = value
    }
  }
  return query
}

/** The audit Filters of a panel that counts audit-log rows (issue 1063, decision D2 A): Action and
 * User. The panel sets Entity itself, and Action lists only the triage actions, the only ones
 * that its rows have. */
export const PANEL_AUDIT_FIELDS: readonly FilterField[] = AUDIT_FIELDS.filter((f) => f.key !== 'entity').map((f) =>
  f.key === 'action' && f.type === 'terms' ? { ...f, values: TRIAGE_ACTIONS } : f,
)

/** The audit filters of a panel in words, one text for each. */
export function panelAuditFilterParts(filters: AuditFilters): string[] {
  return filters ? presetParts(PANEL_AUDIT_FIELDS, filters as ViewPreset) : []
}

/** The audit read of a panel: its query with its audit filters. A panel with none sends its query
 * as it is. */
export function panelAuditQuery<Q extends { cluster_id: string }>(base: Q, filters: AuditFilters): Q & Record<string, unknown> {
  if (panelAuditFilterParts(filters).length === 0) return base
  const params = Object.fromEntries(
    Object.entries(filters as Record<string, unknown>).filter(([, v]) => v !== null && v !== undefined),
  )
  return { ...params, ...base }
}

/** The Audit log link of a panel: its audit filters, and the entities that the panel counts. */
export function panelAuditLogQuery(filters: AuditFilters): Record<string, string> {
  return presetToRouteQuery(AUDIT_FIELDS, { ...filters, entity_type: [...TRIAGE_ENTITY_TYPES] } as ViewPreset)
}

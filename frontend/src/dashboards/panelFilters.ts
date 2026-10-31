/**
 * The filters of a dashboard panel (issue 999). A panel stores them in the shape of a saved
 * view's preset, so the saved-view helpers give their words and their Findings link.
 */
import type { ViewPreset } from '@/api/generated'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { presetParts, presetToRouteQuery } from '@/findings/savedViews'

type Filters = ViewPreset | null | undefined

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

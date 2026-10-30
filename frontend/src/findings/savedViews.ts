/**
 * Saved-view capture ⇄ apply (M9f slice 4, schema v2) — the pure mapping between the findings
 * workbench and the stored `{preset, workbench}` pair, golden-pinned. Capture is param-keyed
 * (the preset mirrors SearchFilters); apply is field-keyed (the /findings URL vocabulary,
 * `!`-prefix negation included). Cluster-agnostic by construction: neither direction ever
 * touches cluster_id or an absolute `t` — a deep link carries `?cluster=` separately.
 */
import type { ViewPreset, ViewWorkbench } from '@/api/generated'
import { termQueryValues } from '@/filters/buildFilterQuery'
import {
  isNegatable,
  valueLabel,
  type FilterField,
  type Selections,
  type TermsField,
} from '@/filters/fields.config'
import type { Modes } from '@/stores/filters'

/** localStorage keys shared with FindingsView (the Columns-menu persistence — applying a view
 * writes the same keys the menu writes, so the table reads it natively on mount). */
export const FINDINGS_COLS_KEY = 'javv.findings.hidden_cols'
export const FINDINGS_ORDER_KEY = 'javv.findings.col_order'
export const FINDINGS_DENSE_KEY = 'javv.findings.dense'

/** Current selections + modes (+ the trend window for the `new` flag) → the stored preset. */
export function captureLens(
  fields: readonly FilterField[],
  selections: Selections,
  modes: Modes,
  windowDays: number,
): ViewPreset {
  const preset: Record<string, unknown> = {}
  for (const field of fields) {
    const selected = selections[field.key] ?? []
    if (selected.length === 0) continue
    if (field.type === 'terms') {
      const values = termQueryValues(field, selected)
      const not = field.negatable && (modes[field.key] ?? 'is') === 'not'
      const param = not ? `exclude_${field.param}` : field.param
      preset[param] = field.multi ? values : values[0]
    } else if (field.type === 'flags') {
      for (const flag of field.values) {
        if (!selected.includes(flag.key)) continue
        if (flag.window) {
          preset[flag.param] = Math.min(365, Math.max(1, Math.ceil(windowDays)))
        } else {
          preset[flag.param] = true
        }
      }
    } else {
      const not = isNegatable(field) && (modes[field.key] ?? 'is') === 'not'
      const param = not ? `exclude_${field.param}` : field.param
      const texts = selected.map((v) => v.trim()).filter((t) => t && t.length >= (field.minLength ?? 1))
      if (texts.length > 0) preset[param] = field.multi ? texts : texts[0]
    }
  }
  return preset as ViewPreset
}

/** Stored preset → the /findings route query (SCREENS §6: the deep-link round-trip must
 * reproduce identical query params — buildFilterQuery over this query re-emits the preset). */
export function presetToRouteQuery(
  fields: readonly FilterField[],
  preset: ViewPreset,
): Record<string, string> {
  const p = preset as Record<string, unknown>
  const query: Record<string, string> = {}
  const attr: string[] = []
  for (const field of fields) {
    if (field.type === 'terms') {
      const inc = termValues(p[field.param])
      const exc = termValues(p[`exclude_${field.param}`])
      if (exc.length > 0) query[field.key] = exc.map((v) => `!${v}`).join(',')
      else if (inc.length > 0) query[field.key] = inc.join(',')
    } else if (field.type === 'flags') {
      for (const flag of field.values) {
        const v = p[flag.param]
        if (flag.window ? typeof v === 'number' : v === true) attr.push(flag.key)
      }
      if (attr.length > 0) query[field.key] = attr.join(',')
    } else {
      // a negated text field round-trips through the same `!` prefix as a terms field
      const exc = textValues(field, p[`exclude_${field.param}`])
      const inc = textValues(field, p[field.param])
      if (exc.length > 0) query[field.key] = exc.map((v) => `!${v}`).join(',')
      else if (inc.length > 0) query[field.key] = inc.join(',')
    }
  }
  return query
}

// a stored terms filter is a list, or one string in a view saved before issue 949; an empty list
// is no filter, as on the server
function termValues(v: unknown): unknown[] {
  if (v === undefined || v === null) return []
  return Array.isArray(v) ? v : [v]
}

// a stored text filter is a list (issue 949), or one string in a view saved before; a field that
// takes one value on screen applies the first
function textValues(field: FilterField, v: unknown): string[] {
  const all = (Array.isArray(v) ? v : [v]).filter((s): s is string => typeof s === 'string' && s !== '')
  return field.type === 'text' && field.multi ? all : all.slice(0, 1)
}

const names = (field: FilterField, values: unknown[]): string =>
  values.map((v) => valueLabel(field, String(v))).join(', ')

/** The filters of a preset in words, one text for each ("severity is none of low, negligible",
 * "KEV"). Field labels come from the same config that renders the pills. */
export function presetParts(fields: readonly FilterField[], preset: ViewPreset): string[] {
  const p = preset as Record<string, unknown>
  const parts: string[] = []
  for (const field of fields) {
    if (field.type === 'terms') {
      const exc = termValues(p[`exclude_${field.param}`])
      const inc = termValues(p[field.param])
      if (exc.length > 0) {
        parts.push(`${field.label} is ${exc.length > 1 ? 'none of' : 'not'} ${names(field, exc)}`)
      } else if (inc.length > 0) {
        parts.push(`${field.label} ${inc.length > 1 ? 'is one of' : 'is'} ${names(field, inc)}`)
      }
    } else if (field.type === 'flags') {
      for (const flag of field.values) {
        const v = p[flag.param]
        if (flag.window ? typeof v === 'number' : v === true) parts.push(flag.label)
      }
    } else {
      const exc = textValues(field, p[`exclude_${field.param}`]).map((v) => `"${v}"`)
      const inc = textValues(field, p[field.param]).map((v) => `"${v}"`)
      if (exc.length > 0) parts.push(`${field.label} is ${exc.length > 1 ? 'none of' : 'not'} ${exc.join(', ')}`)
      else if (inc.length === 1) parts.push(`${field.label} ${inc[0]}`)
      else if (inc.length > 1) parts.push(`${field.label} is one of ${inc.join(', ')}`)
    }
  }
  return parts
}

/** One-line human summary of a preset for the card ("severity is none of low, negligible ·
 * KEV"). */
export function presetSummary(fields: readonly FilterField[], preset: ViewPreset): string {
  return presetParts(fields, preset).join(' · ') || 'No filters: everything'
}

/** The API query for the card's live server count (SCREENS §6): the preset params verbatim
 * plus the tenant, against /findings/facets — a size-0 agg. NEVER /findings here: that path
 * opens a PIT per call, so a page of cards would leak cursors and trip the per-principal
 * concurrency cap (bit live, 2026-07-17). The total is the severity-bucket sum — every row
 * carries exactly one severity_canonical. */
export function presetCountQuery(
  preset: ViewPreset,
  clusterId: string,
  asOf?: string,
): Record<string, unknown> {
  // the card sums only the severity facet (facetsTotal), so the other facets are not asked for
  const query: Record<string, unknown> = { cluster_id: clusterId, fields: ['severity'] }
  if (asOf !== undefined) query.as_of = asOf
  for (const [k, v] of Object.entries(preset as Record<string, unknown>)) {
    if (v !== null && v !== undefined) query[k] = v
  }
  return query
}

/** Facets response (the `{facets: {...}}` envelope) → the card count (null = degraded). */
export function facetsTotal(body: unknown): number | null {
  const severity = (body as { facets?: { severity?: { count: number }[] } } | null)?.facets
    ?.severity
  if (!Array.isArray(severity)) return null
  return severity.reduce((sum, b) => sum + (b.count ?? 0), 0)
}

/** True when the terms field on this preset is negated — the card chips echo the pill look. */
export function isExcluded(field: TermsField, preset: ViewPreset): boolean {
  const v = (preset as Record<string, unknown>)[`exclude_${field.param}`]
  return v !== undefined && v !== null
}

export type { ViewPreset, ViewWorkbench }

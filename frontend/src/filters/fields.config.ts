/**
 * The one `fields` config that drives BOTH FacetRail and FilterBar (PLAN gate: adding a field
 * here surfaces it in both with no component edits). Shape mirrors the backend contract, not
 * the prototype: `severity`, `state`, `ptype`, `namespace` and `assignee` take several values,
 * and so do the text fields `image`, `cve` and `package` (issue 949); `scanner` and the other text
 * fields send one; KEV / fix-available / disagree are boolean flags (grouped as one "Attribute"
 * facet, as in the prototype).
 */
import { stateLabel } from '@/findings/stateLabels'
import { SEVERITIES } from '@/styles/tokens'

// the most values one list filter takes: mirrors the backend's MAX_FILTER_VALUES (docs/API.md,
// filters), so a pick past it never sends a query the API refuses with 422
export const MAX_FILTER_VALUES = 32

interface BaseField {
  key: string
  label: string
}

/** Enumerated values → one query param. `multi` only where the backend accepts an array. */
export interface TermsField extends BaseField {
  type: 'terms'
  param: string
  multi?: boolean
  /** Field name in the facets response; omit for fields with no aggregation. */
  facetKey?: string
  /** The most buckets the server gives for this field, when it is not FACET_CAP. It must equal
   * the size of the server's count for the field (issue 983). */
  facetCap?: number
  /** Static vocabulary; omit to take values from the facet buckets. Only a field with this list
   * sends its values in lower case (`termQueryValues`). */
  values?: readonly string[]
  /** The backend has an `exclude_<param>` mirror (issue 349) — the bar offers is/is not and
   * the URL carries `!`-prefixed values. Only findings fields today. */
  negatable?: boolean
  /** What a stored value is called on screen. The value itself (URL, API param, saved view)
   * never changes; only the rail, the pills and summaries print this. Omit for values that
   * are already the real name of a thing (a scanner, a namespace). */
  valueLabel?: (value: string) => string
}

/** A group of independent boolean params rendered as one facet group. A `window` flag emits
 * the picker's trend-window days instead of `true` — the "new in range" event lens. */
export interface FlagsField extends BaseField {
  type: 'flags'
  values: readonly {
    key: string
    param: string
    label: string
    window?: boolean
    /** Hover explanation for non-obvious flags (rail row title). */
    hint?: string
  }[]
}

/** Free-text param (no facet buckets), one value unless `multi`. `minLength` mirrors the API's own
 * validation — a keystroke must never emit a known-invalid query (contract-guard, audit 343). */
export interface TextField extends BaseField {
  type: 'text'
  param: string
  minLength?: number
  /** Same `exclude_<param>` mirror as a terms field. A text field can carry it because some
   * of these params are EXACT terms server-side (`image_repo` is a `term` clause, not a
   * wildcard) — the free-text input is just the entry affordance, not the match semantics. */
  negatable?: boolean
  /** The param takes several values (issue 949): each Enter in the filter bar adds one, and a
   * second pick from a table cell adds rather than replaces. Off by default. */
  multi?: boolean
}

export type FilterField = TermsField | FlagsField | TextField

/** Does this field have an `exclude_<param>` twin to negate into? Flags never do — absence
 * and negation are different questions (issue 349 §1). One helper so the six places that ask
 * cannot drift apart. */
/** The display name of one value of a field: a flag's label, a terms field's `valueLabel`,
 * else the value as stored. The rail, the pills and the saved-view summary all print this. */
export function valueLabel(field: FilterField, value: string): string {
  if (field.type === 'flags') return field.values.find((v) => v.key === value)?.label ?? value
  if (field.type === 'terms' && field.valueLabel) return field.valueLabel(value)
  return value
}

export const isNegatable = (field: FilterField): boolean =>
  field.type !== 'flags' && field.negatable === true

/**
 * Which mode a value is currently filtered under, or `null` when it is not selected at all —
 * what a `ValueActions` pair needs to show the active side as pressed (issue 349 §2).
 *
 * Here rather than in each table: every grid asked the same question and four copies of the
 * answer is three too many.
 */
export function activeMode(
  fieldKey: string,
  value: string,
  selections: Selections | undefined,
  modes: Record<string, 'is' | 'not'> | undefined,
): 'is' | 'not' | null {
  if (!(selections?.[fieldKey] ?? []).includes(value)) return null
  return modes?.[fieldKey] ?? 'is'
}

/** Active selections, keyed by field key. A one-value field holds a single-entry array. */
export type Selections = Record<string, string[]>

export const emptySelections = (fields: readonly FilterField[]): Selections =>
  Object.fromEntries(fields.map((f) => [f.key, []]))

/** A flag and a field whose include side the backend refuses together (`FILTER_PAIRS` in
 * backend/src/backend/query/search.py). The exclude side stays free: "assignee is not bob" with
 * Unassigned is a valid question. */
export interface ExclusivePair {
  flagField: string
  flag: string
  field: string
}

/** Findings screen config (FR-12). Owned here; M9b+ screens import, never copy. */
export const FINDINGS_FIELDS: readonly FilterField[] = [
  // the rail search box writes this — CONTAINS across cve/image/namespace/assignee/package
  { key: 'q', label: 'Search', type: 'text', param: 'q', minLength: 2 },
  { key: 'severity', label: 'Severity', type: 'terms', param: 'severity', multi: true, facetKey: 'severity', values: SEVERITIES, negatable: true },
  { key: 'scanner', label: 'Scanner', type: 'terms', param: 'scanner', facetKey: 'scanner', values: ['trivy', 'grype'], negatable: true },
  {
    key: 'attr',
    label: 'Attribute',
    type: 'flags',
    values: [
      { key: 'kev', param: 'kev', label: 'KEV' },
      { key: 'fixable', param: 'fixable', label: 'Fix available' },
      { key: 'disagree', param: 'disagree', label: 'Scanners disagree' },
      // issue 363: ranges on the materialized D21 group clock against the LIVE SLA policy —
      // exactly the rows whose SLA cell reads overdue (chip ≡ filter, pinned server-side)
      {
        key: 'overdue',
        param: 'overdue',
        label: 'SLA breached',
        hint:
          'Findings past their SLA deadline under the current policy: the same rows whose ' +
          'SLA column shows overdue. Handled findings (risk-accepted, not-affected, resolved) ' +
          'are never counted.',
      },
      {
        key: 'unassigned',
        param: 'unassigned',
        label: 'Unassigned',
        hint:
          'Findings nobody owns yet: the untriaged backlog. This is absence, not exclusion: ' +
          '"assignee is not <someone>" keeps unowned rows too, so it can never ask this.',
      },
      // first_seen_at within the global range — the event view of the state table
      {
        key: 'new',
        param: 'new_within_days',
        label: 'New in range',
        window: true,
        hint:
          'Only findings first seen inside the selected time range. A quiet range shows 0. ' +
          'Off, the table shows everything currently present.',
      },
    ],
  },
  { key: 'state', label: 'State', type: 'terms', param: 'state', multi: true, facetKey: 'state', values: ['open', 'acknowledged', 'not_affected', 'risk_accepted', 'resolved', 'stale'], negatable: true, valueLabel: stateLabel },
  { key: 'ptype', label: 'Package type', type: 'terms', param: 'ptype', multi: true, facetKey: 'ptype', negatable: true },
  // rail dims are top-N by count (server caps at 32); the value-search in Add-filter still
  // reaches anything the rail's cap hides
  { key: 'namespace', label: 'Namespace', type: 'terms', param: 'namespace', multi: true, facetKey: 'namespaces', negatable: true },
  // `image_repo` is an exact `term` server-side, so the grid's image cell can filter on the
  // row's FULL repo — and negate it, since `exclude_image_repo` exists (issue 349 §2)
  { key: 'image', label: 'Image', type: 'text', param: 'image_repo', multi: true, negatable: true },
  // issue 492 completes the negation family. Both are exact `term`s server-side and neither
  // is a facet — package cardinality is unbounded, and one CVE per bucket is not a rail dim —
  // so they are bar-and-cell fields, like `image` above.
  { key: 'cve', label: 'CVE', type: 'text', param: 'cve_id', multi: true, negatable: true },
  { key: 'package', label: 'Package', type: 'text', param: 'package_name', multi: true, negatable: true },
  { key: 'assignee', label: 'Assignee', type: 'terms', param: 'assignee', multi: true, facetKey: 'assignee', negatable: true },
]

/** The one pair the Findings filters can send: the store keeps one mode per field, so a field
 * never goes out with its own `exclude_` side. */
export const FINDINGS_EXCLUSIVE_PAIRS: readonly ExclusivePair[] = [
  { flagField: 'attr', flag: 'unassigned', field: 'assignee' },
]

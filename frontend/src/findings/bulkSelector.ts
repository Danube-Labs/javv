/**
 * Grid lens → M5d bulk selector (M9b slice 4). The shipped contract is SELECTOR-based (a frozen
 * server-side id-set from cve_id/image_digest/severity/state/assignee predicates) — NOT a list
 * of checked rows. Anything the selector can't express (scanner, KEV/fixable/disagree flags,
 * namespace, image_repo, ptype, multi-value severity/state/assignee) must BLOCK the bulk
 * action, never silently widen it: a selector that ignores an active filter would triage MORE
 * rows than the operator is looking at.
 */
import type { FilterField } from '@/filters/fields.config'

export interface BulkSelector {
  severity?: string
  state?: string
  assignee?: string
}

export interface LensResult {
  selector: BulkSelector | null
  /** User-facing reason the current lens is not bulk-expressible (null = expressible). */
  blocked: string | null
}

/** Selector-expressible filter keys and how they map. */
const EXPRESSIBLE: Record<string, keyof BulkSelector> = {
  severity: 'severity',
  state: 'state',
  assignee: 'assignee',
}

export function lensToSelector(
  fields: readonly FilterField[],
  selections: Record<string, string[]>,
  modes: Record<string, 'is' | 'not'> = {},
): LensResult {
  const selector: BulkSelector = {}
  const inexpressible: string[] = []
  let multi: string | null = null

  for (const field of fields) {
    const values = selections[field.key] ?? []
    if (values.length === 0) continue
    const target = EXPRESSIBLE[field.key]
    if ((modes[field.key] ?? 'is') === 'not') {
      // the selector contract has no exclude side (issue 349) — an excluded field must
      // block, or bulk would triage the rows the operator deliberately filtered OUT
      inexpressible.push(`${field.label} (excluded)`)
    } else if (!target) {
      inexpressible.push(field.label)
    } else if (values.length > 1) {
      multi = field.label
    } else {
      selector[target] = values[0]
    }
  }

  if (inexpressible.length > 0) {
    return {
      selector: null,
      blocked:
        `Remove ${inexpressible.length === 1 ? 'this filter' : 'these filters'} first: ` +
        `${inexpressible.join(', ')}. Bulk triage only follows Severity, State and Assignee, ` +
        'so it would change more findings than you see.',
    }
  }
  if (multi) {
    return {
      selector: null,
      blocked: `Pick a single ${multi} value. Bulk triage works on exactly one at a time.`,
    }
  }
  if (Object.keys(selector).length === 0) {
    return {
      selector: null,
      blocked:
        'Add a filter first. Bulk triage changes every finding that matches your filters, ' +
        'so it needs a severity, a state or an assignee to work on.',
    }
  }
  return { selector, blocked: null }
}

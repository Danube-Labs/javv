/**
 * Filter-selection store factory: one store instance per screen (findings, audit, images…),
 * all sharing this logic — selections keyed by the screen's `fields` config, serialized
 * to/from the route query so filtered views are shareable URLs (bolt M9a).
 *
 * URL format: one query param per field key, values comma-joined (`?severity=critical,high`).
 * Field keys never collide with the global params (`cluster_id` lives in the store, `as_of`
 * under its own key).
 *
 * Negation (issue 349): a NEGATABLE terms field carries a per-field mode — `is` (include,
 * the default) or `not` (exclude). The URL spells `not` as a `!` prefix on every value
 * (`?severity=!low,!negligible`); a field is one mode or the other, never mixed.
 */
import { defineStore } from 'pinia'
import type { LocationQuery } from 'vue-router'

import {
  emptySelections,
  isNegatable,
  type FilterField,
  type Selections,
} from '@/filters/fields.config'

export type FilterMode = 'is' | 'not'
export type Modes = Record<string, FilterMode>

/** `maxValues` caps a multi field where the API does (Findings: 32, issue 949); a screen that
 * filters in the browser leaves it unset. */
export function makeFiltersStore(
  storeId: string,
  fields: readonly FilterField[],
  maxValues = Number.POSITIVE_INFINITY,
) {
  return defineStore(storeId, {
    state: () => ({ selections: emptySelections(fields) as Selections, modes: {} as Modes }),
    getters: {
      hasFilters: (s) => Object.values(s.selections).some((v) => v.length > 0),
      activeFields: (s) => fields.filter((f) => (s.selections[f.key] ?? []).length > 0),
      modeOf: (s) => (fieldKey: string) => s.modes[fieldKey] ?? 'is',
    },
    actions: {
      toggle(fieldKey: string, value: string) {
        const field = fields.find((f) => f.key === fieldKey)
        if (!field) return
        const current = this.selections[fieldKey] ?? []
        if (current.includes(value)) {
          this.selections[fieldKey] = current.filter((v) => v !== value)
        } else if (field.type === 'terms' && !field.multi) {
          this.selections[fieldKey] = [value] // single-value param: replace, never accumulate
        } else if (current.length >= maxValues) {
          return // the API refuses a longer list; the rail and the filter bar say so
        } else {
          this.selections[fieldKey] = [...current, value]
        }
      },
      setText(fieldKey: string, value: string) {
        this.selections[fieldKey] = value.trim() ? [value.trim()] : []
      },
      clearField(fieldKey: string) {
        this.selections[fieldKey] = []
        delete this.modes[fieldKey]
      },
      clearAll() {
        this.selections = emptySelections(fields)
        this.modes = {}
      },
      /**
       * Pick a value straight INTO a mode — the rail/grid value actions (issue 349 §2), where
       * the operator names the side instead of toggling a checkbox and then flipping the pill.
       *
       * Clicking the side a value already sits on clears it, so the same control undoes itself.
       *
       * The one case worth stating: a field carries ONE mode by design (see the header), so
       * moving a field to the OTHER mode cannot keep its existing values — their meaning would
       * silently invert. Entering the other mode therefore starts a fresh selection with just
       * the clicked value, and the pill shows that result immediately rather than hiding it.
       */
      pickValue(fieldKey: string, value: string, mode: FilterMode) {
        const field = fields.find((f) => f.key === fieldKey)
        if (!field || field.type === 'flags') return
        if (mode === 'not' && !isNegatable(field)) return
        const current = this.modes[fieldKey] ?? 'is'
        if (current !== mode) {
          this.selections[fieldKey] = [value]
          this.setMode(fieldKey, mode)
          return
        }
        // a one-value text field holds one value, so picking it again clears rather than
        // accumulates; a multi one (issue 949) toggles like a terms field
        if (field.type === 'text' && !field.multi) {
          const on = (this.selections[fieldKey] ?? [])[0] === value
          this.selections[fieldKey] = on ? [] : [value]
        } else {
          this.toggle(fieldKey, value)
        }
        if ((this.selections[fieldKey] ?? []).length === 0) delete this.modes[fieldKey]
      },
      setMode(fieldKey: string, mode: FilterMode) {
        const field = fields.find((f) => f.key === fieldKey)
        if (!field || !isNegatable(field)) return
        if (mode === 'is') delete this.modes[fieldKey]
        else this.modes[fieldKey] = mode
      },
      toggleMode(fieldKey: string) {
        this.setMode(fieldKey, (this.modes[fieldKey] ?? 'is') === 'is' ? 'not' : 'is')
      },
      /** Route query → selections (unknown keys and unknown vocabulary values are dropped). */
      fromQuery(query: LocationQuery) {
        const next = emptySelections(fields)
        const nextModes: Modes = {}
        for (const field of fields) {
          const raw = query[field.key]
          if (typeof raw !== 'string' || raw === '') continue
          let values = [...new Set(raw.split(',').filter(Boolean))]
          if (isNegatable(field) && values.some((v) => v.startsWith('!'))) {
            // any `!` flips the whole field to exclude (one mode per field, never mixed)
            nextModes[field.key] = 'not'
            values = values.map((v) => (v.startsWith('!') ? v.slice(1) : v)).filter(Boolean)
          }
          if (field.type === 'text') {
            // a shared URL can carry under-minLength text — drop it here so the chip never
            // shows a filter the builder refuses to emit (contract-guard, audit 343)
            const min = field.minLength ?? 1
            const kept = field.multi ? values.slice(0, maxValues) : values.slice(0, 1)
            next[field.key] = kept.filter((v) => v.trim().length >= min)
          } else if (field.type === 'flags') {
            const known = new Set(field.values.map((v) => v.key))
            next[field.key] = values.filter((v) => known.has(v))
          } else if (field.values) {
            const known = new Set(field.values)
            const kept = values.filter((v) => known.has(v))
            next[field.key] = field.multi ? kept.slice(0, maxValues) : kept.slice(0, 1)
          } else {
            next[field.key] = field.multi ? values.slice(0, maxValues) : values.slice(0, 1)
          }
        }
        this.selections = next
        this.modes = nextModes
      },
      /** Selections → route query fragment (empty fields omitted; excluded fields `!`-prefix
       * every value). */
      toQuery(): Record<string, string> {
        const query: Record<string, string> = {}
        for (const field of fields) {
          const values = this.selections[field.key] ?? []
          if (values.length === 0) continue
          const not = (this.modes[field.key] ?? 'is') === 'not'
          query[field.key] = values.map((v) => (not ? `!${v}` : v)).join(',')
        }
        return query
      },
    },
  })
}

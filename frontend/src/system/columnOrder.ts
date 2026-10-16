/**
 * Column-order state for the findings grid (task 92) — pure, unit-tested.
 *
 * One saved order drives both drag surfaces: header drag in the table (PrimeVue
 * `reorderableColumns`, indexes over the RENDERED columns) and row drag in the Columns menu
 * (indexes over the FULL key list, hidden included). Hidden keys keep their slot in the full
 * order, so hiding + reordering + re-showing never scrambles a column the user parked.
 */

/** Validated restore: unknown keys drop, missing known keys append (a new column released
 * after the user saved an order still appears); garbage degrades to the default. */
export function restoreOrder(raw: string | null, known: readonly string[]): string[] {
  try {
    const parsed: unknown = JSON.parse(raw ?? '')
    if (Array.isArray(parsed)) {
      const saved = parsed.filter((k): k is string => typeof k === 'string' && known.includes(k))
      if (saved.length > 0) return [...saved, ...known.filter((k) => !saved.includes(k))]
    }
  } catch {
    /* garbage degrades to the default order */
  }
  return [...known]
}

/** Validated restore of the hidden columns: unknown keys drop; garbage degrades to the default
 * set. An empty list is kept, since it is the user showing every column. */
export function restoreHidden(
  raw: string | null,
  known: readonly string[],
  defaults: readonly string[],
): Set<string> {
  try {
    const parsed: unknown = JSON.parse(raw ?? '')
    if (Array.isArray(parsed)) {
      return new Set(parsed.filter((k): k is string => typeof k === 'string' && known.includes(k)))
    }
  } catch {
    /* garbage degrades to the default set */
  }
  return new Set(defaults)
}

/**
 * Header drag → new full order. `dragIndex`/`dropIndex` are PrimeVue's, counted over the
 * rendered columns: `pinnedLeft` fixed columns, then the visible orderable ones (a trailing
 * pinned column only ever appears as a drop target past the end — clamped). Returns null
 * when the drag is a no-op or started on a pinned column.
 */
export function reorderFromDrag(
  order: readonly string[],
  hidden: ReadonlySet<string>,
  dragIndex: number,
  dropIndex: number,
  pinnedLeft: number,
): string[] | null {
  const visible = order.filter((k) => !hidden.has(k))
  const from = dragIndex - pinnedLeft
  if (from < 0 || from >= visible.length) return null
  const to = Math.min(Math.max(dropIndex - pinnedLeft, 0), visible.length - 1)
  if (to === from) return null
  const next = [...visible]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved!)
  let vi = 0
  return order.map((k) => (hidden.has(k) ? k : next[vi++]!))
}

/** Menu drag → new full order: move `key` to `toIndex` (clamped). Null on no-op/unknown key. */
export function moveKey(order: readonly string[], key: string, toIndex: number): string[] | null {
  const from = order.indexOf(key)
  if (from === -1) return null
  const to = Math.min(Math.max(toIndex, 0), order.length - 1)
  if (to === from) return null
  const next = [...order]
  next.splice(from, 1)
  next.splice(to, 0, key)
  return next
}

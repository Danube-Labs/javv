/**
 * Where a popover goes next to the element it belongs to: on its right when there is room, else
 * on its left, else over its top edge under the trigger, else above the trigger. With `under`, the
 * last two are under the whole element, else above it, so a wide element stays in view (issue
 * 1205: the Triage cell at full width). Viewport coordinates, as `getBoundingClientRect` gives
 * them, for a `position: fixed` popover.
 */
export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}
export interface Size {
  width: number
  height: number
}
export interface Point {
  x: number
  y: number
}
export interface Placed {
  left: number
  top: number
  side: 'right' | 'left' | 'below' | 'above'
  /** where the arrow sits along the popover edge that faces the trigger, in px from its start */
  arrow: number
}

export const POPOVER_GAP = 14
export const POPOVER_MARGIN = 12
const ARROW_INSET = 16

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, Math.max(lo, hi)))

/**
 * The place on whole pixels: the boxes of a page come in part pixels, and a card on a part pixel
 * draws its edge and its arrow soft and stepped (issue 1240).
 */
export function placeBeside(anchor: Box, size: Size, view: Size, trigger?: Point, under = false): Placed {
  const placed = place(anchor, size, view, trigger, under)
  const left = Math.round(placed.left)
  const top = Math.round(placed.top)
  // the arrow moves with the rounded edge, so its tip stays within half a pixel of the trigger
  const across = placed.side === 'below' || placed.side === 'above'
  const shift = across ? placed.left - left : placed.top - top
  const length = across ? size.width : size.height
  return { ...placed, left, top, arrow: clamp(Math.round(placed.arrow + shift), ARROW_INSET, length - ARROW_INSET) }
}

function place(anchor: Box, size: Size, view: Size, trigger: Point | undefined, under: boolean): Placed {
  const point = trigger ?? { x: anchor.right, y: anchor.top + ARROW_INSET }
  let side: Placed['side'] = 'below'
  let left = clamp(anchor.right - size.width, POPOVER_MARGIN, view.width - size.width - POPOVER_MARGIN)
  if (anchor.right + POPOVER_GAP + size.width <= view.width - POPOVER_MARGIN) {
    side = 'right'
    left = anchor.right + POPOVER_GAP
  } else if (anchor.left - POPOVER_GAP - size.width >= POPOVER_MARGIN) {
    side = 'left'
    left = anchor.left - POPOVER_GAP - size.width
  }
  if (side === 'below') {
    // under a wide element the trigger can be anywhere along it: centre on the trigger
    if (under) left = clamp(point.x - size.width / 2, POPOVER_MARGIN, view.width - size.width - POPOVER_MARGIN)
    const arrow = clamp(point.x - left, ARROW_INSET, size.width - ARROW_INSET)
    const below = under ? anchor.bottom + POPOVER_GAP : anchor.top + POPOVER_GAP
    if (below + size.height <= view.height - POPOVER_MARGIN) {
      return { left, top: below, side, arrow }
    }
    if (under) {
      const top = clamp(anchor.top - POPOVER_GAP - size.height, POPOVER_MARGIN, view.height - size.height - POPOVER_MARGIN)
      return { left, top, side: 'above', arrow }
    }
    // no room under the top edge: above the trigger, the arrow pointing down at it
    const top = clamp(point.y - POPOVER_GAP - size.height, POPOVER_MARGIN, view.height - size.height - POPOVER_MARGIN)
    return { left, top, side: 'above', arrow }
  }
  const top = clamp(point.y - ARROW_INSET - 6, POPOVER_MARGIN, view.height - size.height - POPOVER_MARGIN)
  return { left, top, side, arrow: clamp(point.y - top, ARROW_INSET, size.height - ARROW_INSET) }
}

/**
 * The start point of the genie motion: the tip of the arrow, 6px out of the edge that faces the
 * trigger, as `transform-origin` and the centre of the `clip-path` reveal (issue 1240).
 */
export function pourOrigin(placed: Placed): string {
  const at = `${placed.arrow}px`
  if (placed.side === 'right') return `-6px ${at}`
  if (placed.side === 'left') return `calc(100% + 6px) ${at}`
  if (placed.side === 'below') return `${at} -6px`
  return `${at} calc(100% + 6px)`
}

/**
 * True when the arrow points from the head band of the popover, so a dark head gives the arrow
 * its color: below the element the arrow is on the top edge, on a side it is where its middle
 * falls, and above the trigger it is on the bottom edge (issue 1205).
 */
export function arrowOnHead(placed: Placed, headHeight: number): boolean {
  if (placed.side === 'below') return true
  if (placed.side === 'above') return false
  return placed.arrow < headHeight
}

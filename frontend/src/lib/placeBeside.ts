/**
 * Where a popover goes next to the element it belongs to: on its right when there is room, else
 * on its left, else over its top edge under the trigger, else above the trigger. Viewport
 * coordinates, as `getBoundingClientRect` gives them, for a `position: fixed` popover.
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

export function placeBeside(anchor: Box, size: Size, view: Size, trigger?: Point): Placed {
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
    const arrow = clamp(point.x - left, ARROW_INSET, size.width - ARROW_INSET)
    if (anchor.top + POPOVER_GAP + size.height <= view.height - POPOVER_MARGIN) {
      return { left, top: anchor.top + POPOVER_GAP, side, arrow }
    }
    // no room under the top edge: above the trigger, the arrow pointing down at it
    const top = clamp(point.y - POPOVER_GAP - size.height, POPOVER_MARGIN, view.height - size.height - POPOVER_MARGIN)
    return { left, top, side: 'above', arrow }
  }
  const top = clamp(point.y - ARROW_INSET - 6, POPOVER_MARGIN, view.height - size.height - POPOVER_MARGIN)
  return { left, top, side, arrow: clamp(point.y - top, ARROW_INSET, size.height - ARROW_INSET) }
}

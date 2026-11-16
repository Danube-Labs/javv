/**
 * The kit popover (issue 440, option B for the panel settings): where it goes next to its
 * element, and the dismiss contract of DESIGN.md §2 (Escape, a click outside, a visible ✕).
 */
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { h, nextTick } from 'vue'

import PopoverShell from '@/components/ui/PopoverShell.vue'
import { arrowOnHead, placeBeside, POPOVER_GAP, POPOVER_MARGIN } from '@/lib/placeBeside'

const view = { width: 1440, height: 900 }
const size = { width: 380, height: 300 }
const box = (left: number, top: number, right: number, bottom: number) => ({ left, top, right, bottom })

describe('the arrow on a dark head (issue 1205)', () => {
  it('below the element, the arrow points from the top edge, so from the head', () => {
    expect(arrowOnHead({ left: 0, top: 0, side: 'below', arrow: 40 }, 60)).toBe(true)
  })
  it('above the trigger, the arrow points from the bottom edge, never from the head', () => {
    expect(arrowOnHead({ left: 0, top: 0, side: 'above', arrow: 40 }, 60)).toBe(false)
  })
  it('on a side, the arrow is on the head only while its middle is inside the head', () => {
    expect(arrowOnHead({ left: 0, top: 0, side: 'right', arrow: 30 }, 60)).toBe(true)
    expect(arrowOnHead({ left: 0, top: 0, side: 'left', arrow: 59 }, 60)).toBe(true)
    expect(arrowOnHead({ left: 0, top: 0, side: 'right', arrow: 60 }, 60)).toBe(false)
    expect(arrowOnHead({ left: 0, top: 0, side: 'right', arrow: 200 }, 60)).toBe(false)
  })
})

describe('where the popover goes', () => {
  it('on the right of a panel in the left column, with the arrow at the trigger', () => {
    const placed = placeBeside(box(270, 340, 820, 830), size, view, { x: 720, y: 332 })
    expect(placed.side).toBe('right')
    expect(placed.left).toBe(820 + POPOVER_GAP)
    expect(placed.arrow).toBe(332 - placed.top)
  })

  it('on the left of a panel in the right column', () => {
    const placed = placeBeside(box(850, 340, 1400, 830), size, view, { x: 1300, y: 332 })
    expect(placed.side).toBe('left')
    expect(placed.left).toBe(850 - POPOVER_GAP - size.width)
  })

  it('over the top edge of a full panel, under its trigger, inside the screen', () => {
    const placed = placeBeside(box(270, 340, 1400, 600), size, view, { x: 1300, y: 332 })
    expect(placed.side).toBe('below')
    expect(placed.left).toBe(1400 - size.width)
    expect(placed.top).toBe(340 + POPOVER_GAP)
    expect(placed.arrow).toBe(1300 - placed.left)
  })

  it('above the trigger of a full panel low on the screen, the arrow pointing down at it', () => {
    const placed = placeBeside(box(270, 860, 1400, 1300), size, view, { x: 1300, y: 852 })
    expect(placed.side).toBe('above')
    expect(placed.top).toBe(852 - POPOVER_GAP - size.height)
    expect(placed.arrow).toBe(1300 - placed.left)
  })

  it('under the element, when a panel asks for it and no side has room (issue 1205)', () => {
    // a full-width Triage cell with its trigger at the foot: the popover must not cover the cell
    const placed = placeBeside(box(270, 300, 1400, 560), size, view, { x: 500, y: 540 }, true)
    expect(placed.side).toBe('below')
    expect(placed.top).toBe(560 + POPOVER_GAP)
    // centred on the trigger, so the arrow points at it and not at the far end of the cell
    expect(placed.left).toBe(500 - size.width / 2)
    expect(placed.arrow).toBe(size.width / 2)
  })

  it('above the element, when a panel asks to go under it but the screen has no room there', () => {
    const placed = placeBeside(box(270, 500, 1400, 760), size, view, { x: 500, y: 740 }, true)
    expect(placed.side).toBe('above')
    expect(placed.top).toBe(500 - POPOVER_GAP - size.height)
  })

  it('a side wins over the place under the element', () => {
    const placed = placeBeside(box(850, 340, 1150, 830), size, view, { x: 1000, y: 800 }, true)
    expect(placed.side).toBe('left')
  })

  it('stays inside the screen when the panel is near an edge', () => {
    const low = placeBeside(box(270, 820, 820, 1300), size, view, { x: 720, y: 812 })
    expect(low.top).toBe(view.height - size.height - POPOVER_MARGIN)
    const high = placeBeside(box(270, -200, 820, 300), size, view, { x: 720, y: -208 })
    expect(high.top).toBe(POPOVER_MARGIN)
    // the arrow never leaves the rounded edge of the card
    expect(high.arrow).toBeGreaterThanOrEqual(16)
  })
})

describe('the popover', () => {
  let wrappers: ReturnType<typeof mount>[] = []
  afterEach(() => {
    for (const w of wrappers) w.unmount()
    wrappers = []
    document.body.innerHTML = ''
  })

  function mountPopover() {
    const anchor = document.createElement('div')
    const trigger = document.createElement('button')
    const elsewhere = document.createElement('button')
    document.body.append(anchor, trigger, elsewhere)
    trigger.focus()
    const w = mount(PopoverShell, {
      props: { title: 'Panel settings', subtitle: 'Top components', anchor, trigger },
      slots: { default: () => h('button', { class: 'inside' }, 'Half') },
      attachTo: document.body,
    })
    wrappers.push(w)
    return { w, trigger, elsewhere }
  }

  it('is a dialog named after its panel, with its own close button, and takes the focus', async () => {
    const { w } = mountPopover()
    await nextTick()
    await nextTick()
    const card = w.find('[role="dialog"]')
    expect(card.attributes('aria-label')).toBe('Panel settings: Top components')
    expect(card.attributes('aria-modal')).toBeUndefined()
    expect(document.activeElement).toBe(card.element)
    await w.find('[aria-label="Close"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('has a light head unless a panel turns on the dark band of the window heads (issue 1205)', async () => {
    const { w } = mountPopover()
    await nextTick()
    expect(w.find('.pop-head').classes()).not.toContain('pop-head--band')
    expect(w.find('.ui-close').classes()).not.toContain('ui-close--dark')
    await w.setProps({ band: true })
    expect(w.find('.pop-head').classes()).toContain('pop-head--band')
    expect(w.find('.ui-close').classes()).toContain('ui-close--dark')
  })

  it('closes on Escape and on a click outside, but not on a click inside or on its trigger', async () => {
    const { w, trigger, elsewhere } = mountPopover()
    await nextTick()
    w.find('.inside').element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    trigger.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    expect(w.emitted('close')).toBeUndefined()
    elsewhere.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    expect(w.emitted('close')).toHaveLength(1)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toHaveLength(2)
  })

  it('goes to its place again when its content grows, so its foot stays inside the screen (issue 999)', async () => {
    let grew: (() => void) | null = null
    let watched: Element | null = null
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(cb: () => void) {
          grew = cb
        }
        observe(el: Element) {
          watched = el
        }
        disconnect() {}
      },
    )
    try {
      const { w, trigger } = mountPopover()
      // a trigger low on the screen, as the settings of a panel at the foot of a dashboard
      trigger.getBoundingClientRect = () => ({ ...box(700, 690, 760, 710), width: 60, height: 20 }) as DOMRect
      await nextTick()
      const card = w.find('[role="dialog"]')
      let height = 300
      Object.defineProperty(card.element, 'offsetHeight', { get: () => height })
      grew!()
      await nextTick()
      expect(watched).toBe(card.element)
      const top = () => parseFloat((card.element as HTMLElement).style.top)
      expect(top() + 300).toBeLessThanOrEqual(window.innerHeight - POPOVER_MARGIN)
      // a filter row more: the card is taller, and it moves up so its foot stays on the screen
      height = 600
      grew!()
      await nextTick()
      expect(top() + 600).toBeLessThanOrEqual(window.innerHeight - POPOVER_MARGIN)
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('gives the focus back to its trigger when it closes', async () => {
    const { w, trigger } = mountPopover()
    await nextTick()
    w.unmount()
    wrappers = []
    expect(document.activeElement).toBe(trigger)
  })
})

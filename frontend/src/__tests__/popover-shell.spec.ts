/**
 * The kit popover (issue 440, option B for the panel settings): where it goes next to its
 * element, and the dismiss contract of DESIGN.md §2 (Escape, a click outside, a visible ✕).
 */
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { h, nextTick } from 'vue'

import PopoverShell from '@/components/ui/PopoverShell.vue'
import { placeBeside, POPOVER_GAP, POPOVER_MARGIN } from '@/lib/placeBeside'

const view = { width: 1440, height: 900 }
const size = { width: 380, height: 300 }
const box = (left: number, top: number, right: number, bottom: number) => ({ left, top, right, bottom })

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

  it('gives the focus back to its trigger when it closes', async () => {
    const { w, trigger } = mountPopover()
    await nextTick()
    w.unmount()
    wrappers = []
    expect(document.activeElement).toBe(trigger)
  })
})

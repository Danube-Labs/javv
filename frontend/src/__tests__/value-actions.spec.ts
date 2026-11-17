import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ValueActions from '@/components/filters/ValueActions.vue'

/**
 * The include/exclude pair (issue 349 §2). Tested as a pure unit — what it emits and what a
 * screen reader hears — never through a host screen.
 */
describe('ValueActions', () => {
  const base = { field: 'Namespace', value: 'kube-system' }
  const btns = (w: ReturnType<typeof mount>) => w.findAll('.val-act-btn')

  it('offers both sides and emits the mode it was asked for', async () => {
    const w = mount(ValueActions, { props: base })
    expect(btns(w)).toHaveLength(2)
    await btns(w)[0]!.trigger('click')
    await btns(w)[1]!.trigger('click')
    expect(w.emitted('pick')).toEqual([['is'], ['not']])
  })

  it('names the field AND the value, so the action is never a bare "exclude"', () => {
    const w = mount(ValueActions, { props: base })
    expect(btns(w)[0]!.attributes('aria-label')).toBe('Filter to namespace kube-system')
    expect(btns(w)[1]!.attributes('aria-label')).toBe('Filter out namespace kube-system')
  })

  it('says the display name where the stored value is not what the screen shows', () => {
    const w = mount(ValueActions, {
      props: { field: 'State', value: 'not_affected', shown: 'Not affected' },
    })
    expect(btns(w)[0]!.attributes('aria-label')).toBe('Filter to state Not affected')
    expect(btns(w)[1]!.attributes('title')).toBe('Filter out state Not affected')
  })

  it('the active side reads as pressed, and its label offers the undo', () => {
    const w = mount(ValueActions, { props: { ...base, active: 'not' } })
    expect(btns(w)[1]!.classes()).toContain('val-act-on')
    expect(btns(w)[1]!.attributes('aria-pressed')).toBe('true')
    expect(btns(w)[1]!.attributes('aria-label')).toBe(
      'Clear exclusion of namespace kube-system',
    )
    expect(btns(w)[0]!.attributes('aria-pressed')).toBe('false')
  })

  it('drops the include side where the host already owns it (the rail row click)', () => {
    const w = mount(ValueActions, { props: { ...base, excludeOnly: true } })
    expect(btns(w)).toHaveLength(1)
    expect(btns(w)[0]!.attributes('aria-label')).toBe('Filter out namespace kube-system')
  })

  /** `.fpill-x`, the pattern this follows, is mouse-only. This one must not repeat that. */
  it('is operable by keyboard, unlike the .fpill-x it is modelled on', async () => {
    const w = mount(ValueActions, { props: base })
    expect(btns(w)[1]!.attributes('tabindex')).toBe('0')
    await btns(w)[1]!.trigger('keydown.enter')
    await btns(w)[1]!.trigger('keydown.space')
    expect(w.emitted('pick')).toEqual([['not'], ['not']])
  })

  /**
   * The pixel-grid snap (issue 349 §2). The grid puts this bar on a fractional origin, which
   * smeared its 2px marks across three device pixels — differently per axis, so the plus's two
   * strokes read as different weights. jsdom has no layout, so the ARITHMETIC is pinned here
   * and the real geometry in `tests/e2e/value-actions.spec.ts`.
   */
  describe('pixel-grid snap', () => {
    afterEach(() => {
      vi.restoreAllMocks()
      vi.unstubAllGlobals()
    })

    /** jsdom has neither DOMMatrixReadOnly nor a transform in getComputedStyle, so both are
     *  modelled: `applied` is the translate the browser would have on screen RIGHT NOW —
     *  mid-transition it lags the written `--snap-*`, which is exactly the bug this pins. */
    const mountIn = (origin: { left: number; top: number }) => {
      const host = document.createElement('td')
      document.body.appendChild(host)
      const w = mount(ValueActions, { props: base, attachTo: host })
      const el = w.element as HTMLElement
      const applied = { x: 0, y: 0 }
      vi.spyOn(el, 'getBoundingClientRect').mockImplementation(
        () => ({ left: origin.left + applied.x, top: origin.top + applied.y }) as DOMRect,
      )
      vi.spyOn(window, 'getComputedStyle').mockImplementation(
        () => ({ transform: `matrix(1, 0, 0, 1, ${applied.x}, ${applied.y})` }) as CSSStyleDeclaration,
      )
      vi.stubGlobal(
        'DOMMatrixReadOnly',
        class {
          m41: number
          m42: number
          constructor(t: string) {
            const p = /matrix\(([^)]+)\)/.exec(t)![1]!.split(',').map(Number)
            this.m41 = p[4]!
            this.m42 = p[5]!
          }
        },
      )
      const written = () => ({
        x: parseFloat(el.style.getPropertyValue('--snap-x')) || 0,
        y: parseFloat(el.style.getPropertyValue('--snap-y')) || 0,
      })
      /** The transition has finished: what is on screen equals what was written. */
      const settle = () => Object.assign(applied, written())
      const hover = () => host.dispatchEvent(new MouseEvent('mouseenter'))
      hover()
      return { el, applied, written, settle, hover }
    }

    it('offsets by the negative fraction, so the bar lands on a whole pixel', () => {
      const { el } = mountIn({ left: 695.36, top: 410.25 })
      expect(el.style.getPropertyValue('--snap-x')).toBe('-0.36px')
      expect(el.style.getPropertyValue('--snap-y')).toBe('-0.25px')
    })

    it('is a no-op when the origin is already whole — no phantom transform', () => {
      const { written } = mountIn({ left: 700, top: 400 })
      expect(written()).toEqual({ x: 0, y: 0 })
    })

    /** The rect ALWAYS includes the applied translate; without subtracting it back out, each
     *  pass would snap relative to the last and walk the bar off position. */
    it('re-measuring does not drift — the second pass agrees with the first', () => {
      const { el, settle, hover } = mountIn({ left: 695.36, top: 410.25 })
      const first = el.style.getPropertyValue('--snap-x')
      settle()
      hover()
      settle()
      hover()
      expect(el.style.getPropertyValue('--snap-x')).toBe(first)
    })

    /**
     * The regression that shipped as CI red on #496: re-hover INSIDE the 120ms lift, where the
     * applied transform is the snap plus the animation's leftover. Subtracting the last WRITTEN
     * snap (the old code) baked that leftover into the new value — the snap corrupted itself.
     * The fix subtracts the live matrix, so a mid-flight measurement still lands the settled value.
     */
    it('re-measuring mid-transition does not bake the animation offset into the snap', () => {
      const { applied, written, hover } = mountIn({ left: 695.36, top: 410.25 })
      expect(written()).toEqual({ x: -0.36, y: -0.25 })
      // mouse left and came straight back: the reverse lift is ~2/3 done, so the on-screen
      // translate is the snap plus a fraction of the 4px rise the transition is still unwinding
      applied.x = -0.36
      applied.y = -0.25 + 4 * 0.318
      hover()
      expect(written()).toEqual({ x: -0.36, y: -0.25 })
    })
  })

  /** It nests inside the rail row's <button>; an un-stopped click would also toggle the row. */
  it('never lets its click reach the host row', async () => {
    let hostClicks = 0
    const w = mount(
      {
        components: { ValueActions },
        template: `<button @click="$emit('host')"><ValueActions v-bind="p" /></button>`,
        props: ['p'],
      },
      { props: { p: base }, attrs: { onHost: () => (hostClicks += 1) } },
    )
    await w.find('.val-act-btn').trigger('click')
    expect(hostClicks).toBe(0)
  })
})

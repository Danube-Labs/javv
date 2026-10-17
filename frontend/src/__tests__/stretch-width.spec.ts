/**
 * useStretchWidth (issue 902, operator decision D3 A): a box that gets wider stretches from its old
 * width to its new one; a box that gets narrower changes at once; reduced motion stops it; the box
 * gets its own styles back. jsdom has no layout and no Element.animate, so the test gives the box a
 * width and records the animations.
 */
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'

import { useStretchWidth } from '@/composables/useStretchWidth'

/** The width each text gives the box; a text not listed gives 120px. */
let widths = new Map<string, number>()
let reduced = false
type FakeRun = { keyframes: Keyframe[]; options: KeyframeAnimationOptions; cancelled: boolean; onfinish: (() => void) | null }
let runs: FakeRun[] = []

beforeEach(() => {
  widths = new Map()
  reduced = false
  runs = []
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (this: HTMLElement) {
    return { width: widths.get(this.textContent ?? '') ?? 120 } as DOMRect
  })
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: reduced && q.includes('reduce') }) as MediaQueryList)
  HTMLElement.prototype.animate = function (keyframes: Keyframe[], options: KeyframeAnimationOptions) {
    const run: FakeRun = { keyframes, options, cancelled: false, onfinish: null }
    runs.push(run)
    return {
      cancel: () => (run.cancelled = true),
      set onfinish(fn: (() => void) | null) {
        run.onfinish = fn
      },
      get onfinish() {
        return run.onfinish
      },
    } as unknown as Animation
  } as typeof HTMLElement.prototype.animate
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const Card = defineComponent({
  props: { text: { type: String, required: true } },
  setup(props) {
    const box = ref<HTMLElement | null>(null)
    useStretchWidth(box)
    return () => h('div', { ref: box, class: 'card', style: 'overflow: visible' }, props.text)
  },
})

/** Changes the text and the width the box will have after the change. */
async function grow(w: ReturnType<typeof mount>, text: string, to: number) {
  widths.set(text, to)
  await w.setProps({ text })
  await nextTick()
}

describe('useStretchWidth', () => {
  it('stretches from the old width to the new one, on the motion tokens', async () => {
    const w = mount(Card, { props: { text: 'Fleet current state' } })
    await grow(w, 'Fleet current state · 34 clusters · 33 need attention', 300)
    expect(runs).toHaveLength(1)
    expect(runs[0]!.keyframes).toEqual([{ width: '120px' }, { width: '300px' }])
    expect(runs[0]!.options.duration).toBe(200)
    expect(runs[0]!.options.easing).toBe('cubic-bezier(0.16, 1, 0.3, 1)')
  })

  it('clips and keeps the text on one line during the stretch, then gives back the own styles', async () => {
    const w = mount(Card, { props: { text: 'a' } })
    await grow(w, 'a longer text', 300)
    const el = w.get('.card').element as HTMLElement
    expect(el.style.overflow).toBe('hidden')
    expect(el.style.whiteSpace).toBe('nowrap')
    runs[0]!.onfinish?.()
    expect(el.style.overflow).toBe('visible')
    expect(el.style.whiteSpace).toBe('')
  })

  it('a box that gets narrower, or keeps its width, changes at once', async () => {
    widths.set('a long text', 300)
    const w = mount(Card, { props: { text: 'a long text' } })
    await grow(w, 'short', 80)
    await grow(w, 'same', 80)
    expect(runs).toHaveLength(0)
  })

  it('does not move with reduced motion', async () => {
    reduced = true
    const w = mount(Card, { props: { text: 'a' } })
    await grow(w, 'a longer text', 300)
    expect(runs).toHaveLength(0)
  })

  it('a second change during a stretch ends the first at once and starts from there', async () => {
    const w = mount(Card, { props: { text: 'a' } })
    await grow(w, 'a longer text', 200)
    await grow(w, 'a still longer text', 320)
    expect(runs).toHaveLength(2)
    expect(runs[0]!.cancelled).toBe(true)
    expect(runs[1]!.keyframes).toEqual([{ width: '200px' }, { width: '320px' }])
    runs[1]!.onfinish?.()
    expect((w.get('.card').element as HTMLElement).style.overflow).toBe('visible')
  })

  it('ends a stretch under way when the component unmounts', async () => {
    const w = mount(Card, { props: { text: 'a' } })
    await grow(w, 'a longer text', 300)
    w.unmount()
    expect(runs[0]!.cancelled).toBe(true)
  })
})

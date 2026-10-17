/**
 * A box that gets wider when its content grows stretches to the right, from its old width to its
 * new one, instead of jumping in one frame (issue 902, operator decision D3 A). Use it on a box
 * that sizes to its text, such as a header card whose note gets longer when the data arrives.
 *
 * This animates width, which the design rules permit in two places only: here and the sidebar
 * collapse (DESIGN.md §9, enforced by style-rules.spec.ts). It runs on the calling component's
 * own updates: the width is read before the update and after it. A box that gets narrower changes
 * at once. During the stretch the text does not wrap and the box clips it, so the text shows from
 * left to right as the box grows.
 */
import { onBeforeUpdate, onUnmounted, onUpdated, type Ref } from 'vue'

/** A motion token from tokens.css, with the same value as a fallback when no style sheet loaded. */
function motionToken(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

/** A CSS time in milliseconds. The production build writes `200ms` as `.2s`, so read both units. */
export function cssTimeMs(value: string): number {
  const n = parseFloat(value)
  return value.trim().endsWith('ms') ? n : n * 1000
}

export function useStretchWidth(box: Ref<HTMLElement | null>) {
  let before = 0
  let running: { animation: Animation; restore: () => void } | undefined

  /** Ends the stretch under way and gives the box back its own styles, at once. */
  function stop() {
    if (!running) return
    running.animation.onfinish = null
    running.animation.cancel()
    running.restore()
    running = undefined
  }

  onBeforeUpdate(() => {
    before = box.value?.getBoundingClientRect().width ?? 0
  })

  onUpdated(() => {
    const el = box.value
    if (!el || !before) return
    stop()
    const after = el.getBoundingClientRect().width
    if (after - before < 1 || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const style = { overflow: el.style.overflow, whiteSpace: el.style.whiteSpace }
    el.style.overflow = 'hidden'
    el.style.whiteSpace = 'nowrap'
    const restore = () => {
      el.style.overflow = style.overflow
      el.style.whiteSpace = style.whiteSpace
    }
    const animation = el.animate([{ width: `${before}px` }, { width: `${after}px` }], {
      duration: cssTimeMs(motionToken('--dur-panel', '200ms')),
      easing: motionToken('--ease-out', 'cubic-bezier(0.16, 1, 0.3, 1)'),
    })
    running = { animation, restore }
    animation.onfinish = () => {
      restore()
      running = undefined
    }
  })

  onUnmounted(stop)
}

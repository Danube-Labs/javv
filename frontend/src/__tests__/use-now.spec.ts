/**
 * useNow (issue 787): the clock as a ref that moves every `ms` while its component is mounted,
 * and stops with it.
 */
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import { useNow } from '@/composables/useNow'

afterEach(() => {
  vi.useRealTimers()
})

function host(ms: number) {
  let now: { value: number } = { value: 0 }
  const w = mount(
    defineComponent({
      setup() {
        now = useNow(ms)
        return () => h('div')
      },
    }),
  )
  return { w, now: () => now.value }
}

describe('useNow', () => {
  it('starts at the clock and moves on each tick', () => {
    vi.useFakeTimers({ now: 1_000_000, toFake: ['Date', 'setInterval', 'clearInterval'] })
    const { w, now } = host(60_000)
    expect(now()).toBe(1_000_000)
    vi.advanceTimersByTime(59_999)
    expect(now()).toBe(1_000_000)
    vi.advanceTimersByTime(1)
    expect(now()).toBe(1_060_000)
    w.unmount()
  })

  it('stops when its component unmounts', () => {
    vi.useFakeTimers({ now: 1_000_000, toFake: ['Date', 'setInterval', 'clearInterval'] })
    const { w } = host(60_000)
    expect(vi.getTimerCount()).toBe(1)
    w.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})

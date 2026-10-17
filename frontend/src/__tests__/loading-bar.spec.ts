/**
 * UiLoadingBar (issue 902, decision D1 B): no bar for work shorter than 250 ms, a bar that grows
 * while the work goes on, and a full bar that fades when it ends. Work that stops and starts again
 * in a short gap keeps one bar.
 */
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import UiLoadingBar from '@/components/ui/UiLoadingBar.vue'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

const scale = (w: ReturnType<typeof mount>) =>
  Number(/scaleX\(([\d.]+)\)/.exec(w.get('.ui-lb-fill').attributes('style') ?? '')?.[1])
const isOn = (w: ReturnType<typeof mount>) => w.classes().includes('ui-lb-on')

describe('UiLoadingBar', () => {
  it('shows nothing for work that ends inside 250 ms', async () => {
    const w = mount(UiLoadingBar, { props: { busy: true } })
    await vi.advanceTimersByTimeAsync(240)
    expect(isOn(w)).toBe(false)
    await w.setProps({ busy: false })
    await vi.advanceTimersByTimeAsync(1000)
    expect(isOn(w)).toBe(false)
    expect(w.attributes('aria-hidden')).toBe('true')
  })

  it('shows after 250 ms of work, then grows more slowly and never reaches the end', async () => {
    const w = mount(UiLoadingBar, { props: { busy: true } })
    await vi.advanceTimersByTimeAsync(260)
    expect(isOn(w)).toBe(true)
    expect(w.attributes('role')).toBe('progressbar')
    expect(w.attributes('aria-hidden')).toBeUndefined()
    await vi.advanceTimersByTimeAsync(500)
    const early = scale(w)
    await vi.advanceTimersByTimeAsync(500)
    const later = scale(w)
    await vi.advanceTimersByTimeAsync(30_000)
    const last = scale(w)
    expect(early).toBeGreaterThan(0.08)
    expect(later).toBeGreaterThan(early)
    expect(later - early).toBeLessThan(early - 0.08)
    expect(last).toBeLessThanOrEqual(0.9)
  })

  it('fills and fades when the work ends, then goes back to empty out of sight', async () => {
    const w = mount(UiLoadingBar, { props: { busy: true } })
    await vi.advanceTimersByTimeAsync(800)
    await w.setProps({ busy: false })
    await vi.advanceTimersByTimeAsync(160)
    expect(scale(w)).toBe(1)
    expect(isOn(w)).toBe(false)
    await vi.advanceTimersByTimeAsync(500)
    expect(scale(w)).toBe(0)
  })

  it('keeps one bar when work ends and starts again inside the gap', async () => {
    const w = mount(UiLoadingBar, { props: { busy: true } })
    await vi.advanceTimersByTimeAsync(600)
    const before = scale(w)
    await w.setProps({ busy: false })
    await vi.advanceTimersByTimeAsync(100)
    await w.setProps({ busy: true })
    await vi.advanceTimersByTimeAsync(300)
    expect(isOn(w)).toBe(true)
    expect(scale(w)).toBeGreaterThan(before)
  })

  it('stops its timers when it unmounts', async () => {
    const w = mount(UiLoadingBar, { props: { busy: true } })
    await vi.advanceTimersByTimeAsync(400)
    w.unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})

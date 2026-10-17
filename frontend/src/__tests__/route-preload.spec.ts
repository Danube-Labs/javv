/**
 * preloadPages (issue 902): the code of each lazy page loads when the browser is idle, one page at
 * a time, and a page that fails to load does not stop the others.
 */
import { describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'

import { preloadPages } from '@/router/preload'

vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn<() => void>(), info: vi.fn<() => void>(), warn: vi.fn<() => void>(), error: vi.fn<() => void>() },
}))

const Page = defineComponent({ render: () => null })

describe('preloadPages', () => {
  it('loads each lazy page once, one at a time, each in its own idle slot', async () => {
    const order: string[] = []
    const lazy = (name: string) => vi.fn<() => Promise<unknown>>(() => (order.push(name), Promise.resolve({ default: Page })))
    const a = lazy('a')
    const b = lazy('b')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: Page },
        { path: '/a', component: a },
        { path: '/shell', component: Page, children: [{ path: 'b', component: b }] },
      ],
    })
    const slots: (() => void)[] = []
    preloadPages(router, (work) => slots.push(work))

    expect(slots).toHaveLength(1)
    expect(order).toEqual([])
    slots.shift()!()
    expect(order).toHaveLength(1)
    await vi.waitFor(() => expect(slots).toHaveLength(1))
    slots.shift()!()
    expect(order.sort()).toEqual(['a', 'b'])
    await Promise.resolve()
    await Promise.resolve()
    expect(slots).toHaveLength(0)
    expect(a).toHaveBeenCalledOnce()
    expect(b).toHaveBeenCalledOnce()
  })

  it('logs a page that fails to load at debug level and goes on with the next', async () => {
    const { logger } = await import('@/lib/logger')
    const ok = vi.fn<() => Promise<unknown>>(() => Promise.resolve({ default: Page }))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/broken', component: () => Promise.reject(new Error('chunk gone')) },
        { path: '/ok', component: ok },
      ],
    })
    preloadPages(router, (work) => work())
    await vi.waitFor(() => expect(ok).toHaveBeenCalledOnce())
    expect(logger.debug).toHaveBeenCalledWith('page_preload_failed', expect.objectContaining({ route: '/broken' }))
  })
})

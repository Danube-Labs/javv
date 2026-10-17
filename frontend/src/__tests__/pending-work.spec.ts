/**
 * pendingWork: the count behind the loading bar (issue 902). It counts each API request until its
 * response arrives and each page change until it settles, and it must never stay above zero after
 * the work ends, or the bar would never go away.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { countedFetch, countNavigations, pendingWork } from '@/system/pendingWork'

const Page = defineComponent({ render: () => null })

beforeEach(() => {
  pendingWork.value = 0
})
afterEach(() => {
  vi.unstubAllGlobals()
})

function deferred() {
  let resolve!: (r: Response) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<Response>((res, rej) => ((resolve = res), (reject = rej)))
  return { promise, resolve, reject }
}

describe('countedFetch', () => {
  it('counts a request from its start until its response, and uses the fetch of that moment', async () => {
    const d = deferred()
    const fetchNow = vi.fn<() => Promise<Response>>(() => d.promise)
    vi.stubGlobal('fetch', fetchNow)
    const call = countedFetch()('/api/v1/findings?x=1')
    expect(fetchNow).toHaveBeenCalledOnce()
    expect(pendingWork.value).toBe(1)
    d.resolve(new Response('{}'))
    await call
    expect(pendingWork.value).toBe(0)
  })

  it('counts a failed request down too', async () => {
    const d = deferred()
    vi.stubGlobal('fetch', () => d.promise)
    const call = countedFetch()(new Request('http://localhost/api/v1/images'))
    expect(pendingWork.value).toBe(1)
    d.reject(new TypeError('network down'))
    await expect(call).rejects.toThrow('network down')
    expect(pendingWork.value).toBe(0)
  })

  it('does not count a request that the caller names as background', async () => {
    const d = deferred()
    vi.stubGlobal('fetch', () => d.promise)
    const seen: { method: string; path: string }[] = []
    const background = (req: { method: string; path: string }) => (seen.push(req), req.path === '/api/v1/notifications')
    const call = countedFetch(background)(new Request('http://localhost/api/v1/notifications?unread=1'))
    expect(pendingWork.value).toBe(0)
    expect(seen).toEqual([{ method: 'GET', path: '/api/v1/notifications' }])
    d.resolve(new Response('{}'))
    await call
    void countedFetch(background)('/api/v1/notifications/read', { method: 'post' })
    expect(seen[1]).toEqual({ method: 'POST', path: '/api/v1/notifications/read' })
    expect(pendingWork.value).toBe(1)
  })
})

describe('countNavigations', () => {
  function makeRouter(routes: Parameters<typeof createRouter>[0]['routes']): Router {
    const router = createRouter({ history: createMemoryHistory(), routes })
    countNavigations(router)
    return router
  }

  it('counts one page change while its page code loads, and settles after it', async () => {
    let load!: (c: unknown) => void
    const router = makeRouter([
      { path: '/', component: Page },
      { path: '/slow', component: () => new Promise((res) => (load = res)) },
    ])
    await router.push('/')
    expect(pendingWork.value).toBe(0)
    const nav = router.push('/slow')
    await vi.waitFor(() => expect(load).toBeTypeOf('function'))
    expect(pendingWork.value).toBe(1)
    load(Page)
    await nav
    expect(pendingWork.value).toBe(0)
  })

  it('a redirect is one page change', async () => {
    const router = makeRouter([
      { path: '/', component: Page },
      { path: '/old', redirect: '/new' },
      { path: '/new', component: Page },
      { path: '/guarded', component: Page, beforeEnter: () => '/new' },
    ])
    await router.push('/old')
    await router.push('/guarded')
    expect(router.currentRoute.value.path).toBe('/new')
    expect(pendingWork.value).toBe(0)
  })

  it('a page change that a newer one cancels stays counted until the newer one settles', async () => {
    let loadA!: (c: unknown) => void
    let loadB!: (c: unknown) => void
    const router = makeRouter([
      { path: '/', component: Page },
      { path: '/a', component: () => new Promise((res) => (loadA = res)) },
      { path: '/b', component: () => new Promise((res) => (loadB = res)) },
    ])
    await router.push('/')
    const first = router.push('/a')
    await vi.waitFor(() => expect(loadA).toBeTypeOf('function'))
    const second = router.push('/b')
    await vi.waitFor(() => expect(loadB).toBeTypeOf('function'))
    loadA(Page)
    await first
    expect(pendingWork.value).toBe(1)
    loadB(Page)
    await second
    expect(pendingWork.value).toBe(0)
    expect(router.currentRoute.value.path).toBe('/b')
  })

  it('settles when the page code fails to load, and on a duplicate or aborted page change', async () => {
    const router = makeRouter([
      { path: '/', component: Page },
      { path: '/broken', component: () => Promise.reject(new Error('chunk gone')) },
      { path: '/blocked', component: Page, beforeEnter: () => false },
    ])
    await router.push('/')
    await router.push('/broken').catch(() => {})
    expect(pendingWork.value).toBe(0)
    await router.push('/')
    await router.push('/blocked')
    expect(pendingWork.value).toBe(0)
  })
})

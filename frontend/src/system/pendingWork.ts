/**
 * The work a user waits for, as one count: the page change under way, if any, and the open API
 * requests. The loading bar in the top bar shows while the count is above zero (issue 902).
 *
 * A background poll must not count, or the bar would show by itself on each poll: the caller
 * names those requests with `isBackground`.
 */
import { shallowRef } from 'vue'
import { isNavigationFailure, NavigationFailureType, type Router } from 'vue-router'

export const pendingWork = shallowRef(0)

function begin() {
  pendingWork.value++
}

function end() {
  pendingWork.value = Math.max(0, pendingWork.value - 1)
}

export type RequestInfo = { method: string; path: string }

/** A `fetch` that counts each request from its start until its response headers arrive. The
 * global `fetch` is looked up on each call, so a test that replaces it after import still works. */
export function countedFetch(isBackground: (req: RequestInfo) => boolean = () => false): typeof fetch {
  return (input, init) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const method = (init?.method ?? (input instanceof Request ? input.method : 'GET')).toUpperCase()
    const path = new URL(url, window.location.origin).pathname
    if (isBackground({ method, path })) return globalThis.fetch(input, init)
    begin()
    return globalThis.fetch(input, init).finally(end)
  }
}

/**
 * Counts one page change from its first guard until it settles. A page change that a newer one
 * cancels stays open, because the newer one settles it; a redirect is one page change for the
 * router (one `afterEach`). An error (for example, the code of the page did not load) never
 * reaches `afterEach`, so `onError` settles it.
 */
export function countNavigations(router: Router) {
  let open = false
  router.beforeEach(() => {
    if (!open) {
      open = true
      begin()
    }
  })
  const settle = () => {
    if (open) {
      open = false
      end()
    }
  }
  router.afterEach((_to, _from, failure) => {
    if (failure && isNavigationFailure(failure, NavigationFailureType.cancelled)) return
    settle()
  })
  router.onError(settle)
}

/**
 * Loads the code of every page while the browser has nothing else to do, one page at a time, so a
 * click shows the new page at once (issue 902). Otherwise the first click on a page waits for all
 * of its code files, with the old page still on the screen.
 *
 * Every route component in this app is either a component object or a lazy `() => import(...)`,
 * so a function here is a lazy page. The browser keeps each loaded module, and the router's own
 * load on the click then resolves at once. A failed load is harmless: the click loads the page
 * again, and a failure there reaches `router.onError`.
 */
import type { Router } from 'vue-router'

import { logger } from '@/lib/logger'

type Idle = (work: () => void) => void

const whenIdle: Idle = (work) =>
  'requestIdleCallback' in window ? window.requestIdleCallback(() => work()) : setTimeout(work, 1)

export function preloadPages(router: Router, idle: Idle = whenIdle) {
  const pages = router
    .getRoutes()
    .flatMap((r) => Object.values(r.components ?? {}).map((c) => ({ path: r.path, c })))
    .filter((p): p is { path: string; c: () => Promise<unknown> } => typeof p.c === 'function')
  const next = (i: number) => {
    const page = pages[i]
    if (!page) return
    idle(() => {
      page
        .c()
        .catch((err: unknown) => logger.debug('page_preload_failed', { route: page.path, message: String(err) }))
        .finally(() => next(i + 1))
    })
  }
  next(0)
}

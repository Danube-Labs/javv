/**
 * The one place the generated client is configured. Same-origin (Vite dev proxy / the deployed
 * ingress route both put the API on our origin); the session cookie is httpOnly and rides
 * automatically. A 502, 503 or 504 anywhere flips the global degraded flag (observability.md §3 —
 * the app degrades loudly, not blindly): the store when the backend's own error envelope says so,
 * the backend for anything else, such as a proxy's 503 page or a gateway's JSON. A 503 whose problem
 * type says the store's disk is full marks the store read-only instead (issue 832). The health
 * store's /readyz poll clears it. Each request counts as pending work for the loading bar, except
 * the background polls below (issue 902).
 */
import { client } from './generated/client.gen'
import { downReason, isBackendProblem, isReadOnlyRefusal, useHealthStore } from '@/stores/health'
import { countedFetch } from '@/system/pendingWork'

/** Requests the app sends by itself on a timer: no user waits for them. */
const BACKGROUND_POLLS = new Set(['/api/v1/notifications'])

client.setConfig({
  baseUrl: '',
  credentials: 'same-origin',
  throwOnError: false,
  fetch: countedFetch((req) => req.method === 'GET' && BACKGROUND_POLLS.has(req.path)),
})

/** The auth routes live at /auth/*, outside /api/v1: their 401 is an answer, not a lost session. */
const isAuthRoute = (url: string) => new URL(url, window.location.origin).pathname.startsWith('/auth/')

client.interceptors.response.use(async (response, request) => {
  if (await isReadOnlyRefusal(response)) {
    useHealthStore().markDegraded('read-only', 'api')
  } else if (response.status === 503 || response.status === 502 || response.status === 504) {
    useHealthStore().markDegraded(downReason(response.status, isBackendProblem(response)), 'api')
  }
  // expired/invalid session: every screen would degrade into generic "unavailable" copy —
  // land on login instead (audit 343). Full navigation on purpose: it also resets stale state.
  // Auth's own endpoints are exempt: a failed sign-in and the signed-out session check answer
  // 401, and a page load on that answer would load the page again (issue 1246).
  if (
    response.status === 401 &&
    !isAuthRoute(request.url) &&
    window.location.pathname !== '/login'
  ) {
    window.location.assign('/login')
  }
  return response
})

export { client }

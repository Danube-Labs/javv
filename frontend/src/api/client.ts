/**
 * The one place the generated client is configured. Same-origin (Vite dev proxy / the deployed
 * ingress route both put the API on our origin); the session cookie is httpOnly and rides
 * automatically. A 502, 503 or 504 anywhere flips the global degraded flag (observability.md §3 —
 * the app degrades loudly, not blindly): the store when the backend's own error envelope says so,
 * the backend for anything else, such as a proxy's 503 page or a gateway's JSON. A 503 whose problem
 * type says the store's disk is full marks the store read-only instead (issue 832). The health
 * store's /readyz poll clears it.
 */
import { client } from './generated/client.gen'
import { downReason, isBackendProblem, isReadOnlyRefusal, useHealthStore } from '@/stores/health'

client.setConfig({ baseUrl: '', credentials: 'same-origin', throwOnError: false })

client.interceptors.response.use(async (response) => {
  if (await isReadOnlyRefusal(response)) {
    useHealthStore().markDegraded('read-only', 'api')
  } else if (response.status === 503 || response.status === 502 || response.status === 504) {
    useHealthStore().markDegraded(downReason(response.status, isBackendProblem(response)), 'api')
  }
  // expired/invalid session: every screen would degrade into generic "unavailable" copy —
  // land on login instead (audit 343). Full navigation on purpose: it also resets stale state.
  // Auth's own endpoints are exempt (login failures ARE 401s the form must render).
  if (
    response.status === 401 &&
    !response.url.includes('/api/v1/auth/') &&
    window.location.pathname !== '/login'
  ) {
    window.location.assign('/login')
  }
  return response
})

export { client }

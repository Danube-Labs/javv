/**
 * Global backend health (observability.md §2/§3): /readyz polled while the app is open; any API
 * 502, 503 or 504 flips `degraded` immediately (via the client interceptor), with the reason. The banner is
 * dismissible-but-recurring — dismissal survives until the NEXT degraded signal, and everything
 * auto-clears when /readyz returns 200. Chrome stays up; data areas show degraded states.
 */
import { defineStore } from 'pinia'
import { STORE_READ_ONLY_TYPE } from '@/api/problem'
import { logger } from '@/lib/logger'

export const POLL_MS = 30_000

/** What is down: the backend itself, or the store behind a backend that still answers. A store
 * that answers but is read-only (its disk full) or red still serves reads (issue 832). */
export type DownReason = 'backend' | 'store' | 'read-only' | 'red'

/**
 * Reads one failed answer. The backend answers a 503 itself when OpenSearch is unreachable, and
 * says so in JSON: `/readyz` with `{"status":"degraded"}`, data routes with the error envelope.
 * Only that 503 means the store. Anything else comes from in front of the backend: the frontend
 * server's 502, a proxy's or an ingress's 502, 503 or 504 page (for a frontend pod that is gone,
 * say), or no answer at all. Then the backend is what is missing (issue 725).
 */
export function downReason(status: number | undefined, fromBackend: boolean): DownReason {
  return status === 503 && fromBackend ? 'store' : 'backend'
}

/** True when an answer is JSON (the /readyz poll then reads its body for the backend's answer). */
export function isBackendJson(response: Response): boolean {
  return /[/+]json\b/.test(response.headers.get('content-type') ?? '')
}

/**
 * True when an API answer is the backend's error envelope (`core/errors.py`, RFC 9457), which every
 * backend error on an API route uses. A gateway's own JSON 503 (Kong, Tyk) is plain JSON.
 */
export function isBackendProblem(response: Response): boolean {
  return /^application\/problem\+json\b/i.test(response.headers.get('content-type') ?? '')
}

/** True when an API answer is the backend saying a write was refused because the store's disk is
 * full. Reads a copy, so the caller still gets the body. */
export async function isReadOnlyRefusal(response: Response): Promise<boolean> {
  if (response.status !== 503 || !isBackendProblem(response)) return false
  try {
    return ((await response.clone().json()) as { type?: unknown }).type === STORE_READ_ONLY_TYPE
  } catch {
    return false
  }
}

/** `read-only` or `red` from a /readyz 200 (`checks.store`), else null. */
async function readyzStoreState(response: Response): Promise<'read-only' | 'red' | null> {
  try {
    const store = ((await response.json()) as { checks?: { store?: unknown } }).checks?.store
    return store === 'read-only' || store === 'red' ? store : null
  } catch {
    return null
  }
}

/** True when a /readyz answer is the backend reporting its store down. */
async function readyzSaysDegraded(response: Response): Promise<boolean> {
  if (response.status !== 503 || !isBackendJson(response)) return false
  try {
    return ((await response.json()) as { status?: unknown }).status === 'degraded'
  } catch {
    return false
  }
}

export const useHealthStore = defineStore('health', {
  state: () => ({ degraded: false, reason: null as DownReason | null, dismissed: false, pollHandle: 0 as ReturnType<typeof setInterval> | 0 }),
  getters: {
    bannerVisible: (s) => s.degraded && !s.dismissed,
    /** The sidebar footer's one-line status. */
    statusLabel: (s) =>
      !s.degraded ? 'Store healthy' : s.reason === 'backend' ? 'Backend not answering' : 'Store degraded',
  },
  actions: {
    markDegraded(reason: DownReason, source: 'api' | 'readyz') {
      if (!this.degraded || this.reason !== reason) logger.warn('backend degraded', { source, reason })
      this.degraded = true
      this.reason = reason
      this.dismissed = false
    },
    dismiss() {
      this.dismissed = true
    },
    async check() {
      try {
        const res = await fetch('/readyz', { credentials: 'same-origin' })
        if (res.ok) {
          const store = await readyzStoreState(res)
          if (store) {
            this.markDegraded(store, 'readyz')
            return
          }
          if (this.degraded) logger.info('backend recovered')
          this.degraded = false
          this.reason = null
        } else {
          this.markDegraded(downReason(res.status, await readyzSaysDegraded(res)), 'readyz')
        }
      } catch {
        this.markDegraded(downReason(undefined, false), 'readyz')
      }
    },
    startPolling() {
      if (this.pollHandle) return
      void this.check()
      this.pollHandle = setInterval(() => void this.check(), POLL_MS)
    },
    stopPolling() {
      if (this.pollHandle) clearInterval(this.pollHandle)
      this.pollHandle = 0
    },
  },
})

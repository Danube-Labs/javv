/**
 * The clock of the backend, as the browser sees it (issue 1291, Q1 B). The backend takes the
 * start of a range from its own clock, so the strips must draw their axis on that clock too: a
 * browser clock that is wrong then changes nothing (ruling 2 of 2026-11-23). Each API response
 * has a `Date` header; the response interceptor of `api/client.ts` keeps the difference between
 * that time and the clock of the browser. The header counts whole seconds, so the backend's time
 * here can be up to a second and the time of the network behind. Before the first response the
 * difference is 0, the clock of the browser.
 */
import { ref } from 'vue'

const offsetMs = ref(0)

/** Keep the difference that the `Date` header of a response gives. */
export function noteServerDate(header: string | null, receivedAtMs: number = Date.now()): void {
  if (header === null) return
  const serverMs = Date.parse(header)
  if (Number.isNaN(serverMs)) return
  offsetMs.value = serverMs - receivedAtMs
}

/** The time now on the clock of the backend. Reactive: a computed that reads it moves when a
 * response changes the difference. */
export function serverNow(browserMs: number = Date.now()): number {
  return browserMs + offsetMs.value
}

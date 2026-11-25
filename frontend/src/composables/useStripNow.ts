/**
 * One "now" for the chart strips of a band (issue 1292, D4 B). Each strip builds its axis up to
 * this time. A strip that read the clock itself kept the time of its first draw: a later read
 * could then answer with buckets past the end of its axis, and two strips that drew on either
 * side of an hour put that hour at two places. This clock is the floor of the current hour, read
 * each minute and shared by every strip, so all axes move at the same moment. The value changes
 * only when the hour changes, so a strip draws again only then. The time is the time of the
 * backend (`system/serverClock.ts`, issue 1291): the backend counts the range from its own clock.
 */
import { computed, onScopeDispose, ref, type ComputedRef } from 'vue'

import { serverNow } from '@/system/serverClock'

const HOUR_MS = 3_600_000
const nowMs = ref(Date.now())
let users = 0
let timer: ReturnType<typeof setInterval> | null = null

export function useStripNow(): ComputedRef<number> {
  users += 1
  nowMs.value = Date.now() // a strip that mounts later moves the band clock for all strips
  if (timer === null) timer = setInterval(() => (nowMs.value = Date.now()), 60_000)
  onScopeDispose(() => {
    users -= 1
    if (users === 0 && timer !== null) {
      clearInterval(timer)
      timer = null
    }
  })
  // the clock of the backend, which takes the start of the range (issue 1291, Q1 B)
  return computed(() => Math.floor(serverNow(nowMs.value) / HOUR_MS) * HOUR_MS)
}

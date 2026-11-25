/**
 * One "now" for the chart strips of a band (issue 1292, D4 B). Each strip builds its axis up to
 * this time. A strip that read the clock itself kept the time of its first draw: a later read
 * could then answer with buckets past the end of its axis, and two strips that drew on either
 * side of an hour put that hour at two places. This clock is read each minute and shared by every
 * strip, so all axes move at the same moment. The time is the time of the backend
 * (`system/serverClock.ts`, issue 1291): the backend counts the range from its own clock.
 */
import { computed, onScopeDispose, ref, type ComputedRef } from 'vue'

import { stripAxis, type IngestInterval } from '@/charts/buildIngestLensOption'
import { serverNow } from '@/system/serverClock'

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
  return computed(() => serverNow(nowMs.value))
}

/** The axis of a strip on the band clock. An exact range starts in the minute of now less its
 * length, so the axis needs the minute (issue 1291). The axis keeps its array while its buckets
 * stay the same, so a strip draws again only when a bucket comes or goes. */
export function useStripAxis(
  range: () => [windowDays: number, t: string | null, interval: IngestInterval],
): ComputedRef<string[]> {
  const now = useStripNow()
  return computed((prev) => {
    const next = stripAxis(...range(), now.value)
    return prev?.length === next.length && prev.every((d, i) => d === next[i]) ? prev : next
  })
}

/**
 * A bar click on an ingest strip → the whole-app T. A bucket maps to its END (the state after
 * its ingests committed, D28); the bucket still in progress means "now". The range keeps its
 * length and only its end moves, labelled with the new end.
 */
import { bucketEndT, type IngestInterval } from '@/charts/buildIngestLensOption'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { lastDataAt } from '@/system/freshness'
import { serverNow } from '@/system/serverClock'

export function useBucketRewind() {
  const timeTravel = useTimeTravelStore()
  return function rewindToBucket(bucketIso: string | undefined, interval: IngestInterval) {
    if (!bucketIso) return
    // the bucket in progress on the clock of the backend, as the axis (issue 1291)
    const t = bucketEndT(bucketIso, serverNow(), interval)
    if (t === null) {
      timeTravel.backToNow()
      return
    }
    timeTravel.rewindTo(t)
    timeTravel.setWindow(timeTravel.windowDays, `→ ${lastDataAt(t)}`)
  }
}

/** Pure view-model for the DigestSubTimeline (unit-tested): ONE scanner's committed
 * scan-events for a repo:tag → digest eras. An era = consecutive runs on the same digest;
 * the boundary between eras is a BUILD CHANGE (never a silent gap); a per-scanner
 * `scan_order` jump inside or before an era is a GAP (cycles that did not observe the tag). */

export interface TimelineEvent {
  scan_order: number
  '@timestamp': string
  scanner: string
  image_digest: string
  total: number
}

export interface DigestEra {
  digest: string
  firstAt: string
  lastAt: string
  runs: number
  /** the era's latest committed finding count (as-scanned, this scanner's) */
  totalAtLast: number
  /** scan_order jumped on entry — cycles between the previous event and this era's first */
  gapBefore: boolean
}

export function digestEras(events: TimelineEvent[], scanner: string): DigestEra[] {
  const own = events
    .filter((e) => e.scanner === scanner)
    .sort((a, b) => a.scan_order - b.scan_order)
  const eras: DigestEra[] = []
  let prevOrder: number | null = null
  for (const e of own) {
    const last = eras.at(-1)
    const gap = prevOrder !== null && e.scan_order - prevOrder > 1
    if (last && last.digest === e.image_digest && !gap) {
      last.lastAt = e['@timestamp']
      last.runs += 1
      last.totalAtLast = e.total
    } else {
      eras.push({
        digest: e.image_digest,
        firstAt: e['@timestamp'],
        lastAt: e['@timestamp'],
        runs: 1,
        totalAtLast: e.total,
        gapBefore: gap,
      })
    }
    prevOrder = e.scan_order
  }
  return eras
}

/** T strictly before this scanner's first committed event = "not yet scanned then". */
export function notYetScannedAt(events: TimelineEvent[], scanner: string, t: string | null): boolean {
  if (t === null) return false
  const first = events
    .filter((e) => e.scanner === scanner)
    .reduce<string | null>((min, e) => (min === null || e['@timestamp'] < min ? e['@timestamp'] : min), null)
  return first !== null ? t < first : true
}

export interface HistorySummary {
  digests: number
  scans: number
  firstAt: string | null
  lastAt: string | null
}

/** The Build history column of the image page (issue 1140, R6): one scanner's committed scans
 * of this repo:tag at or before T, as the card under the band draws them. */
export function historySummary(events: TimelineEvent[], scanner: string, t: string | null): HistorySummary {
  const own = events.filter((e) => e.scanner === scanner && (t === null || e['@timestamp'] <= t))
  const times = own.map((e) => e['@timestamp']).sort()
  return {
    digests: new Set(own.map((e) => e.image_digest)).size,
    scans: own.length,
    firstAt: times[0] ?? null,
    lastAt: times.at(-1) ?? null,
  }
}

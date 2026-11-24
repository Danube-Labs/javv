/** Pure option-builder: the compact ingest-lens variant of the scan-activity chart — same
 * per-scanner bars (never merged), squeezed for the strip above a data table. Short ranges
 * bucket HOURLY (audit 343: a 4-hour scanner cadence is invisible in daily bars). */
import type { EChartsOption } from 'echarts'

import { buildScanActivityOption, type ScanActivityData } from './buildScanActivityOption'

export type IngestInterval = 'day' | 'hour'

export const INTERVAL_MS: Record<IngestInterval, number> = {
  day: 86_400_000,
  hour: 3_600_000,
}

/** Hourly buckets when the span is ≤ 2 days at T=now — the reader path (past T) stays daily. */
export function ingestInterval(windowDays: number, t: string | null): IngestInterval {
  return t === null && windowDays <= 2 ? 'hour' : 'day'
}

/** The dates axis exactly as the option builder ranks it — index-aligned with a bar click's
 * `dataIndex`, so the component can map a click back to its bucket. */
export function ingestLensDates(series: ScanActivityData): string[] {
  return (['trivy', 'grype'].map((s) => series[s as 'trivy' | 'grype']).find((r) => r?.length) ?? []).map(
    (p) => p.date,
  )
}

/** Click-to-rewind T: a bucket maps to its END (state after its ingests committed, D28). A
 * bucket still in progress means "now" — null, the caller's backToNow. */
export function bucketEndT(
  bucketIso: string,
  nowMs: number,
  interval: IngestInterval = 'day',
): string | null {
  const end = new Date(bucketIso).getTime() + INTERVAL_MS[interval] - 1
  return end >= nowMs ? null : new Date(end).toISOString()
}

export const hourLabel = (iso: string): string =>
  new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })

/** The buckets of a strip's range, as the backend counts them (`window_bounds`): from the UTC day
 * floor of the start to the day of the end, or to the hour of now for hourly buckets. A strip
 * that puts each count at its date of this axis lines up with the other strips of its band, also
 * when its last count is in another hour (issue 1292). */
export function stripAxis(
  windowDays: number,
  t: string | null,
  interval: IngestInterval,
  nowMs: number = Date.now(),
): string[] {
  const days = Math.min(365, Math.max(1, Math.ceil(windowDays))) // the days of buildTrendQuery
  const endMs = t === null ? nowMs : Date.parse(t)
  const endDay = Math.floor(endMs / INTERVAL_MS.day) * INTERVAL_MS.day
  const last = interval === 'day' ? endDay : Math.floor(endMs / INTERVAL_MS.hour) * INTERVAL_MS.hour
  const out: string[] = []
  for (let ms = endDay - days * INTERVAL_MS.day; ms <= last; ms += INTERVAL_MS[interval]) {
    out.push(new Date(ms).toISOString())
  }
  return out
}

export function buildIngestLensOption(
  series: ScanActivityData,
  interval: IngestInterval = 'day',
  unit?: string,
): EChartsOption {
  const option = buildScanActivityOption(series, unit)
  if (interval === 'hour') {
    // relabel the axis in hours — the base builder's day labels collapse hourly buckets
    const dates = ingestLensDates(series)
    option.xAxis = {
      ...(option.xAxis as object),
      data: dates.map(hourLabel),
    } as EChartsOption['xAxis']
  }
  return {
    ...option,
    grid: { left: 26, right: 8, top: 6, bottom: 18 },
    // whole-run counts only — a 3-bucket axis on tiny values must not show fractions
    yAxis: { ...(option.yAxis as object), minInterval: 1, splitNumber: 2 },
  }
}

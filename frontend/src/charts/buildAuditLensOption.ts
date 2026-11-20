/** Pure option-builder: the audit lens — journaled events per bucket under the current lens
 * filters (GET /audit/facets `activity`), one accent series in the same compact strip grammar
 * as the ingest lens. Bucket→axis mapping and click-to-rewind reuse the ingest lens helpers
 * (`bucketEndT`, INTERVAL_MS) — one histogram grammar, two data sources. */
import type { EChartsOption } from 'echarts'

import { dayLabel } from '@/lib/format'
import { CHART_ACCENT, CHART_UI } from '@/styles/tokens'

import type { IngestInterval } from './buildIngestLensOption'
import { chartTooltip } from './chartTooltip'

export interface ActivityPoint {
  date: string
  count: number
}

const hourLabel = (iso: string): string =>
  new Date(iso).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false })

export function buildAuditLensOption(
  rows: ActivityPoint[],
  interval: IngestInterval = 'day',
  seriesName = 'events',
): EChartsOption {
  const label = interval === 'hour' ? hourLabel : dayLabel
  return {
    grid: { left: 26, right: 8, top: 6, bottom: 18 },
    legend: { show: false },
    tooltip: chartTooltip('axis'),
    xAxis: {
      type: 'category',
      data: rows.map((p) => label(p.date)),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: CHART_UI.axisLine } },
      axisLabel: {
        color: CHART_UI.label,
        fontSize: 10,
        interval: Math.max(0, Math.floor(rows.length / 7) - 1),
      },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: CHART_UI.splitLine } },
      axisLabel: { color: CHART_UI.label, fontSize: 10 },
      // whole-event counts only — a 3-bucket axis on tiny values must not show fractions
      minInterval: 1,
      splitNumber: 2,
    },
    series: [
      {
        name: seriesName,
        type: 'bar',
        cursor: 'default',
        data: rows.map((p) => p.count),
        itemStyle: { color: CHART_ACCENT, borderRadius: [2, 2, 0, 0] },
        barMaxWidth: 14,
      },
    ],
  }
}

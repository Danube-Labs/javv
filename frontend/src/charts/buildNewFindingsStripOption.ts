/** Pure option-builder: GET /trends/new-findings → the New findings strip (issue 1292). One
 * stacked bar for each bucket, by severity, critical at the bottom. Each count sits at its date
 * of the strip's axis (`stripAxis`), so the strip lines up with Scan ingest above it. Its own y
 * scale: new findings come in hundreds on the day of a new build, and in none on most days. */
import type { BarSeriesOption, EChartsOption } from 'echarts'

import { dayLabel } from '@/lib/format'
import { CHART_SEV, CHART_UI, SEVERITIES, type Severity } from '@/styles/tokens'

import { hourLabel, type IngestInterval } from './buildIngestLensOption'
import { chartTooltip } from './chartTooltip'

export interface NewFindingsPoint {
  date: string
  count: number
}
export type NewFindingsSeries = Partial<Record<Severity, NewFindingsPoint[]>>

export function totalNew(series: NewFindingsSeries): number {
  return Object.values(series).reduce((n, rows) => n + (rows ?? []).reduce((m, p) => m + p.count, 0), 0)
}

export function buildNewFindingsStripOption(
  series: NewFindingsSeries,
  axis: readonly string[],
  interval: IngestInterval,
): EChartsOption {
  const slot = new Map(axis.map((iso, i) => [Date.parse(iso), i]))
  const bars: BarSeriesOption[] = SEVERITIES.flatMap((sev) => {
    const rows = series[sev]
    if (!rows?.length) return []
    const data = axis.map(() => 0)
    for (const p of rows) {
      const i = slot.get(Date.parse(p.date))
      if (i !== undefined) data[i] = p.count
    }
    return [
      {
        name: sev,
        type: 'bar' as const,
        stack: 'new',
        cursor: 'default',
        data,
        itemStyle: { color: CHART_SEV[sev] },
        barMaxWidth: 14,
      },
    ]
  })
  const labels = axis.map(interval === 'hour' ? hourLabel : dayLabel)
  return {
    grid: { left: 26, right: 8, top: 6, bottom: 18 },
    legend: { show: false },
    tooltip: chartTooltip('axis', 'new findings'),
    xAxis: {
      type: 'category',
      data: labels,
      axisLine: { lineStyle: { color: CHART_UI.axisLine } },
      axisLabel: { color: CHART_UI.label, fontSize: 10, interval: Math.max(0, Math.floor(labels.length / 7) - 1) },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      // fewer labels in 56 px: with two splits, 0 to 30 gave four labels that touched. ECharts
      // rounds the step, so some maxima still get three labels (0, 20, 40), which do not touch
      splitNumber: 1,
      splitLine: { lineStyle: { color: CHART_UI.splitLine } },
      axisLabel: { color: CHART_UI.label, fontSize: 10 },
    },
    series: bars,
  }
}

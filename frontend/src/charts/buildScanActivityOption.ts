/** Pure option-builder: GET /trends/scans response → the scan-activity bar chart (committed
 * scan runs per day, one bar series per scanner — never merged). */
import type { BarSeriesOption, EChartsOption } from 'echarts'

import { dayLabel } from '@/lib/format'
import { CHART_SCANNER, CHART_UI } from '@/styles/tokens'

import { chartTooltip } from './chartTooltip'

export interface ScanPoint {
  date: string
  scans: number
}
export type ScanActivityData = Partial<Record<'trivy' | 'grype', ScanPoint[]>>

const SCANNERS = ['trivy', 'grype'] as const

/** `unit` names what a bar counts, in the head of the hover (issue 1292). */
export function buildScanActivityOption(series: ScanActivityData, unit?: string): EChartsOption {
  const dates = (SCANNERS.map((s) => series[s]).find((r) => r?.length) ?? []).map((p) =>
    dayLabel(p.date),
  )

  const bars: BarSeriesOption[] = SCANNERS.flatMap((scanner) => {
    const rows = series[scanner]
    if (!rows?.length) return []
    return [
      {
        name: scanner,
        type: 'bar' as const,
        cursor: 'default',
        data: rows.map((p) => p.scans),
        itemStyle: { color: CHART_SCANNER[scanner], borderRadius: [2, 2, 0, 0] as number[] },
        barMaxWidth: 14,
      },
    ]
  })

  return {
    grid: { left: 34, right: 12, top: 12, bottom: 24 },
    legend: { show: false },
    tooltip: chartTooltip('axis', unit),
    xAxis: {
      type: 'category',
      data: dates,
      axisLine: { lineStyle: { color: CHART_UI.axisLine } },
      axisLabel: { color: CHART_UI.label, fontSize: 10, interval: Math.max(0, Math.floor(dates.length / 7) - 1) },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: CHART_UI.splitLine } },
      axisLabel: { color: CHART_UI.label, fontSize: 10 },
    },
    series: bars,
  }
}

/** Pure option-builder: /trends/findings?split=severity → the severity-lens line chart.
 * One line per D46 canonical bucket in rank order, colored from the pinned severity map.
 * `resolved` stays out of this lens (six dashed twins is noise); the scanner lens keeps the
 * burn-down. Counts are row counts within the selected scanner scope — scoped at the QUERY. */
import type { EChartsOption, LineSeriesOption } from 'echarts'

import { CHART_SEV, CHART_UI, SEVERITIES, type Severity } from '@/styles/tokens'
import type { TrendPoint } from '@/charts/buildFindingsTrendOption'

import { dayLabel } from './axisLabels'

export type SeverityTrendData = Partial<Record<Severity, TrendPoint[]>>

export function buildSeverityTrendOption(data: SeverityTrendData): EChartsOption {
  const dates = (SEVERITIES.map((s) => data[s]).find((r) => r?.length) ?? []).map((p) =>
    dayLabel(p.date),
  )

  const series: LineSeriesOption[] = SEVERITIES.flatMap((sev) => {
    const rows = data[sev]
    if (!rows?.length) return []
    const color = CHART_SEV[sev]
    return [
      {
        name: sev,
        type: 'line' as const,
        cursor: 'default',
        smooth: true,
        symbol: 'none',
        data: rows.map((p) => p.count),
        lineStyle: { width: 2, color },
        itemStyle: { color },
        areaStyle: { color, opacity: 0.05 },
      },
    ]
  })

  return {
    grid: { left: 44, right: 16, top: 16, bottom: 26 },
    legend: { show: false },
    tooltip: {
      trigger: 'axis',
      backgroundColor: CHART_UI.tooltipBg,
      borderWidth: 0,
      textStyle: { color: CHART_UI.tooltipFg, fontSize: 11 },
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: CHART_UI.axisLine } },
      axisLabel: { color: CHART_UI.label, fontSize: 10, interval: Math.max(0, Math.floor(dates.length / 7) - 1) },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      splitLine: { lineStyle: { color: CHART_UI.splitLine } },
      axisLabel: { color: CHART_UI.label, fontSize: 10 },
    },
    series,
  }
}

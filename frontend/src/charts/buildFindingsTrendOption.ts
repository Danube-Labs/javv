/** Pure option-builder: GET /trends/findings response → the "vulnerabilities over time" line
 * chart. Two series SETS, one per scanner, never merged (per-scanner sacred) — new is a solid
 * line, resolved is dashed and labeled scan-observed (A-m9: it is scan resolution, not the
 * human `state=resolved`). Colors/chrome come only from the pinned chart literals. */
import type { EChartsOption, LineSeriesOption } from 'echarts'

import type { ScannerLens } from '@/lib/scannerLens'
import { CHART_SCANNER, CHART_UI } from '@/styles/tokens'

export interface TrendPoint {
  date: string
  count: number
}
export interface FindingsTrendData {
  new: Partial<Record<'trivy' | 'grype', TrendPoint[]>>
  resolved: Partial<Record<'trivy' | 'grype', TrendPoint[]>>
}

const SCANNERS = ['trivy', 'grype'] as const

const dayLabel = (iso: string): string =>
  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

/** What the card says instead of a chart with no lines. The route only returns days for a
 * scanner or severity that has a finding in the range, so "nothing in range" arrives as no
 * series at all, and an axis with no dates reads as a broken chart. */
export function emptyTrendNote(option: EChartsOption, lens: 'scanner' | 'severity'): string | null {
  if ((option.series as unknown[]).length > 0) return null
  return lens === 'scanner'
    ? 'No new or resolved findings in this range.'
    : 'No new findings in this range.'
}

/** The lines of the scanner that the switch selects, or of both. The route gives both scanners
 * at a past T whatever `scanner` it gets, so a panel picks them from the answer. */
export function trendForScanner(data: FindingsTrendData, scanner: ScannerLens): FindingsTrendData {
  if (scanner === 'all') return data
  return { new: { [scanner]: data.new[scanner] }, resolved: { [scanner]: data.resolved[scanner] } }
}

export function buildFindingsTrendOption(data: FindingsTrendData): EChartsOption {
  const dates = (SCANNERS.map((s) => data.new[s]).find((r) => r?.length) ?? []).map((p) =>
    dayLabel(p.date),
  )

  const series: LineSeriesOption[] = []
  for (const scanner of SCANNERS) {
    const color = CHART_SCANNER[scanner]
    const newRows = data.new[scanner]
    if (newRows?.length) {
      series.push({
        name: `new · ${scanner}`,
        type: 'line',
        cursor: 'default',
        smooth: true,
        symbol: 'none',
        data: newRows.map((p) => p.count),
        lineStyle: { width: 2, color },
        itemStyle: { color },
        areaStyle: { color, opacity: 0.06 },
      })
    }
    const resolvedRows = data.resolved[scanner]
    if (resolvedRows?.length) {
      series.push({
        name: `resolved (scan-observed) · ${scanner}`,
        type: 'line',
        cursor: 'default',
        smooth: true,
        symbol: 'none',
        data: resolvedRows.map((p) => p.count),
        lineStyle: { width: 2, color, type: 'dashed' },
        itemStyle: { color },
      })
    }
  }

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

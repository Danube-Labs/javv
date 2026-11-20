import { describe, expect, it } from 'vitest'
import type { EChartsOption } from 'echarts'

import { buildAuditLensOption } from '@/charts/buildAuditLensOption'
import { buildFindingsTrendOption } from '@/charts/buildFindingsTrendOption'
import { buildIngestLensOption } from '@/charts/buildIngestLensOption'
import { buildPtypeDonutOption } from '@/charts/buildPtypeDonutOption'
import { buildScanActivityOption } from '@/charts/buildScanActivityOption'
import { buildSeverityTrendOption } from '@/charts/buildSeverityTrendOption'
import { tooltipContent, type TooltipParam } from '@/charts/chartTooltip'
import { CHART_SCANNER, CHART_UI } from '@/styles/tokens'

const axisParams: TooltipParam[] = [
  { axisValueLabel: '1 Nov', seriesName: 'new · trivy', color: CHART_SCANNER.trivy, value: 31627 },
  { axisValueLabel: '1 Nov', seriesName: 'new · grype', color: CHART_SCANNER.grype, value: null },
]

const texts = (root: HTMLElement, cls: string) =>
  [...root.querySelectorAll(`.${cls}`)].map((el) => el.textContent)

describe('tooltipContent makes the rows of a chart tooltip as DOM nodes', () => {
  it('an axis tooltip shows the axis label, then a row for each series with a dot, a name and a value', () => {
    const root = tooltipContent(axisParams)
    expect(root.classList.contains('chart-tip')).toBe(true)
    expect(texts(root, 'chart-tip-head')).toEqual(['1 Nov'])
    expect(root.querySelectorAll('.chart-tip-row')).toHaveLength(2)
    expect(texts(root, 'chart-tip-name')).toEqual(['new · trivy', 'new · grype'])
    // The app's number format. A day with no value shows the dash, as in ECharts.
    expect(texts(root, 'chart-tip-val')).toEqual(['31,627', '-'])
  })

  it('each dot gets the color of its series', () => {
    const dots = [...tooltipContent(axisParams).querySelectorAll<HTMLElement>('.chart-tip-dot')]
    expect(dots.map((d) => d.style.backgroundColor)).toEqual([
      hexToRgb(CHART_SCANNER.trivy),
      hexToRgb(CHART_SCANNER.grype),
    ])
  })

  it('an item tooltip of the donut is one row with a dot, a name, a value and a share, and has no head', () => {
    const root = tooltipContent({ name: 'os', color: '#1f8e84', value: 31627, percent: 72.03 })
    expect(root.querySelector('.chart-tip-head')).toBeNull()
    expect(root.querySelectorAll('.chart-tip-row')).toHaveLength(1)
    expect(texts(root, 'chart-tip-name')).toEqual(['os'])
    expect(texts(root, 'chart-tip-val')).toEqual(['31,627'])
    expect(texts(root, 'chart-tip-share')).toEqual(['72.03%'])
  })

  it('a name with HTML in it stays text, so scanner data never becomes markup', () => {
    const evil = '<img src=x onerror="alert(1)">'
    const root = tooltipContent([{ axisValueLabel: evil, seriesName: evil, color: '#000', value: 1 }])
    expect(root.querySelector('img')).toBeNull()
    expect(texts(root, 'chart-tip-head')).toEqual([evil])
    expect(texts(root, 'chart-tip-name')).toEqual([evil])
  })

  it('only the dots have a style, and it is only their color, which the policy allows', () => {
    const root = tooltipContent(axisParams)
    const styled = [...root.querySelectorAll('[style]'), ...(root.hasAttribute('style') ? [root] : [])]
    expect(styled.every((el) => el.classList.contains('chart-tip-dot'))).toBe(true)
    for (const el of styled as HTMLElement[]) {
      expect([...el.style].filter((p) => p !== 'background-color')).toEqual([])
    }
  })

  it('a color that is not a string, for example a gradient, gives the dot no color', () => {
    const root = tooltipContent([{ axisValueLabel: 'a', seriesName: 's', color: { type: 'linear' }, value: 2 }])
    expect(root.querySelector<HTMLElement>('.chart-tip-dot')?.style.backgroundColor).toBe('')
  })
})

const pts = (n: number) => [{ date: '2026-07-01T00:00:00.000Z', count: n }]
const scans = { trivy: [{ date: '2026-07-01T00:00:00.000Z', scans: 3 }] }

const builders: [string, EChartsOption, 'axis' | 'item'][] = [
  ['scan activity', buildScanActivityOption(scans), 'axis'],
  ['ingest strip', buildIngestLensOption(scans), 'axis'],
  ['findings trend', buildFindingsTrendOption({ new: { trivy: pts(4) }, resolved: {} }), 'axis'],
  ['severity trend', buildSeverityTrendOption({ critical: pts(4) }), 'axis'],
  ['audit strip', buildAuditLensOption(pts(5)), 'axis'],
  ['package type donut', buildPtypeDonutOption([{ key: 'os', count: 9 }]), 'item'],
]

describe('each chart builder uses the shared tooltip', () => {
  it.each(builders)('%s', (_name, option, trigger) => {
    const tooltip = option.tooltip as Record<string, unknown>
    expect(tooltip.formatter).toBe(tooltipContent)
    expect(tooltip.trigger).toBe(trigger)
    expect(tooltip.backgroundColor).toBe(CHART_UI.tooltipBg)
    // With a named position on an item tooltip, ECharts adds its arrow as HTML with a style attribute.
    expect(typeof tooltip.position).not.toBe('string')
  })
})

function hexToRgb(hex: string): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`
}

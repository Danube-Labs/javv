/** The tooltip of each chart (issue 1272).
 *
 * The frontend server sends a policy (`style-src`, server/serve.mjs) that refuses a `style`
 * attribute in HTML. The default tooltip of ECharts is HTML with such attributes, so a deployed
 * JAVV showed bare text with no dots. This formatter returns DOM nodes. It writes each text with
 * `textContent`. The `.chart-tip` rules of base.css give the layout. The script sets one style
 * only: the color of each dot, through a property of `element.style`. The policy allows that.
 *
 * Do not give `position` a named place, for example 'top'. On an item tooltip, ECharts then adds
 * its arrow as HTML with a style attribute, and the policy refuses it. */
import type { TooltipComponentOption } from 'echarts'

import { fmt } from '@/lib/format'
import { CHART_UI } from '@/styles/tokens'

/** The fields that the tooltip reads from a parameter of an ECharts formatter. */
export interface TooltipParam {
  /** An axis tooltip: the label of the category under the pointer. */
  axisValueLabel?: string
  seriesName?: string
  /** An item tooltip: the name of the item under the pointer, for example a part of the donut. */
  name?: string
  /** A plain color is a string. A gradient is an object, and its dot gets no color. */
  color?: unknown
  value?: unknown
  /** An item tooltip of a pie: the share of the item, in percent. */
  percent?: number
}

function el(tag: string, cls: string, text?: string): HTMLElement {
  const node = document.createElement(tag)
  node.className = cls
  if (text !== undefined) node.textContent = text
  return node
}

const valueText = (v: unknown): string =>
  typeof v === 'number' && Number.isFinite(v) ? fmt(v) : '-'

function row(p: TooltipParam, name: string): HTMLElement {
  const line = el('div', 'chart-tip-row')
  const dot = el('span', 'chart-tip-dot')
  if (typeof p.color === 'string') dot.style.backgroundColor = p.color
  line.append(dot, el('span', 'chart-tip-name', name), el('span', 'chart-tip-val', valueText(p.value)))
  if (typeof p.percent === 'number' && Number.isFinite(p.percent)) line.append(el('span', 'chart-tip-share', `${p.percent}%`))
  return line
}

/** The formatter. An axis tooltip shows the label of its category as a head, then one row for each
 * series. An item tooltip, for example of the donut, is one row with the share of the item.
 * With no rows, it returns an empty string: ECharts then shows no box, as it did with its own
 * tooltip. An empty element gives a dark box with nothing in it. */
export function tooltipContent(params: TooltipParam | TooltipParam[]): HTMLElement | '' {
  const root = el('div', 'chart-tip')
  if (Array.isArray(params)) {
    if (!params.length) return ''
    root.append(el('div', 'chart-tip-head', params[0]?.axisValueLabel ?? ''))
    for (const p of params) root.append(row(p, p.seriesName ?? ''))
  } else {
    root.append(row(params, params.name ?? ''))
  }
  return root
}

/** The tooltip option that each chart builder uses. */
export function chartTooltip(trigger: 'axis' | 'item'): TooltipComponentOption {
  return {
    trigger,
    backgroundColor: CHART_UI.tooltipBg,
    borderWidth: 0,
    textStyle: { color: CHART_UI.tooltipFg, fontSize: 11 },
    formatter: tooltipContent as unknown as TooltipComponentOption['formatter'],
  }
}

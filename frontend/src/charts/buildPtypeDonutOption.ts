/** Pure option-builder: the ptype facet buckets → the package-type donut (B-1 ruled KEPT,
 * backed by the M8d `ptype` facet). Brand-teal categorical ramp — ptype is info-class data,
 * never severity-coded. The caller renders the "awaiting package-type data" placeholder when
 * only `unknown` buckets exist (pre-M8d rows heal on the next sweep, D30). */
import type { EChartsOption } from 'echarts'

import { CHART_PTYPE_RAMP, CHART_UI } from '@/styles/tokens'

import { chartTooltip } from './chartTooltip'

export interface PtypeBucket {
  key: string
  count: number
}

export function buildPtypeDonutOption(buckets: PtypeBucket[]): EChartsOption {
  return {
    legend: { show: false },
    tooltip: chartTooltip('item'),
    series: [
      {
        type: 'pie',
        cursor: 'default',
        radius: ['54%', '82%'],
        center: ['50%', '52%'],
        avoidLabelOverlap: true,
        label: { show: false },
        labelLine: { show: false },
        data: buckets.map((b, i) => ({
          value: b.count,
          name: b.key,
          itemStyle: {
            color: CHART_PTYPE_RAMP[i % CHART_PTYPE_RAMP.length],
            borderColor: CHART_UI.segBorder,
            borderWidth: 1.5,
          },
        })),
      },
    ],
  }
}

/**
 * The two severity bars of an Images row (issue 1127): each scanner's bar gets that scanner's own
 * counts, by the rule the CSV export uses too (`scannerCountsOf`), never one merged mix.
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import MixBar from '@/components/dashboards/MixBar.vue'
import ImagesTable from '@/components/images/ImagesTable.vue'
import type { ImageRow } from '@/stores/images'

/** The API row of nginx 1.21.0 from the install test of issue 1108 (doc scanner grype). */
const nginx: ImageRow = {
  image_digest: 'sha256:47ae43cdfc7064d28800bc42e79a429540c7c80168e8c8952778c0d5af1c09db',
  image_repo: 'docker.io/library/nginx',
  tag: '1.21.0',
  namespaces: ['t1108-apps'],
  scanners: ['grype'],
  crit: 27,
  high: 148,
  med: 190,
  low: 35,
  negligible: 118,
  unknown: 4,
  total: 522,
  fixable: 292,
  replicas: 1,
  trivy_count: 394,
  grype_count: 522,
  count_delta: -128,
  severity_by_scanner: {
    grype: { crit: 27, high: 148, med: 190, low: 35, negligible: 118, unknown: 4, total: 522, fixable: 292 },
    trivy: { crit: 27, high: 138, med: 176, low: 44, negligible: 0, unknown: 9, total: 394, fixable: 309 },
  },
  '@timestamp': '2026-11-07T10:19:31.159520+00:00',
}

function bars(rows: ImageRow[]) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }] })
  const w = mount(ImagesTable, {
    props: { rows, sort: null, order: 'desc', loading: false, filtered: false, hidden: new Set<string>() },
    global: { plugins: [router] },
  })
  return w.findAllComponents(MixBar).map((b) => ({ scanner: b.props('attribution'), counts: b.props('counts') }))
}

beforeEach(() => setActivePinia(createPinia()))

describe('the severity bars of an Images row', () => {
  it("gives each scanner its own counts, also the scanner that is not the doc's own", () => {
    expect(bars([nginx])).toEqual([
      { scanner: 'trivy', counts: { critical: 27, high: 138, medium: 176, low: 44, negligible: 0, unknown: 9 } },
      { scanner: 'grype', counts: { critical: 27, high: 148, medium: 190, low: 35, negligible: 118, unknown: 4 } },
    ])
  })

  it('draws no bar for a scanner with no committed scan', () => {
    const grypeOnly = { ...nginx, severity_by_scanner: { grype: nginx.severity_by_scanner!.grype! } }
    expect(bars([grypeOnly]).map((b) => b.scanner)).toEqual(['grype'])
  })
})

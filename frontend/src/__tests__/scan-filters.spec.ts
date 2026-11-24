import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { SCAN_FILTER_PARAMS, scanFilters } from '@/dashboards/scanFilters'
import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { FINDINGS_FIELDS } from '@/filters/fields.config'

describe('scanFilters (pure): the filters a scan record holds (issue 1293)', () => {
  it('keeps each scan filter, with its exclude side, and leaves out the tenant and the time', () => {
    const query = {
      cluster_id: 'c-1',
      as_of: '2026-11-20T00:00:00Z',
      window_days: 7,
      namespace: ['shop'],
      exclude_image_repo: ['nginx'],
      tag: ['1.4.2'],
      image_digest: 'sha256:abc',
      exclude_scanner: 'grype',
    }
    expect(scanFilters(query)).toEqual({
      applied: {
        namespace: ['shop'],
        exclude_image_repo: ['nginx'],
        tag: ['1.4.2'],
        image_digest: 'sha256:abc',
        exclude_scanner: 'grype',
      },
      ignored: [],
    })
  })

  it('names the other filters that are on, in the order of the query', () => {
    const query = { cluster_id: 'c-1', severity: ['critical'], namespace: ['shop'], kev: true, q: 'openssl', new_within_days: 7 }
    expect(scanFilters(query)).toEqual({
      applied: { namespace: ['shop'] },
      ignored: ['severity', 'kev', 'q', 'new_within_days'],
    })
  })

  it('a scanner other than trivy or grype does not apply: the route refuses it', () => {
    expect(scanFilters({ scanner: 'clair' })).toEqual({ applied: {}, ignored: ['scanner'] })
    expect(scanFilters({ exclude_scanner: 'TRIVY' })).toEqual({ applied: {}, ignored: ['exclude_scanner'] })
    expect(scanFilters({ scanner: 'trivy' }).applied).toEqual({ scanner: 'trivy' })
  })

  it('an empty or unset value is no filter (the saved filters of a panel hold nulls and present)', () => {
    const saved = { namespace: null, tag: [], untagged: false, image_digest: '', kev: null, present: true, exclude_tag: undefined }
    expect(scanFilters(saved)).toEqual({ applied: {}, ignored: [] })
    expect(scanFilters({ untagged: true })).toEqual({ applied: { untagged: true }, ignored: [] })
  })

  it('each filter of the Findings table that a scan record holds goes out with its own name', () => {
    const query = buildFilterQuery(
      FINDINGS_FIELDS,
      { namespace: ['shop'], image: ['nginx'], tag: ['1.4'], digest: ['sha256:abc'], scanner: ['trivy'], attr: ['untagged'] },
      { cluster_id: 'c-1' },
      { namespace: 'not', image: 'is', tag: 'not', scanner: 'not' },
    )
    expect(scanFilters(query)).toEqual({
      applied: {
        exclude_namespace: ['shop'],
        image_repo: ['nginx'],
        exclude_tag: ['1.4'],
        image_digest: 'sha256:abc',
        exclude_scanner: 'trivy',
        untagged: true,
      },
      ignored: [],
    })
  })

  it('the list is the scan filters of the route in openapi.json, no more and no less', () => {
    const spec = JSON.parse(readFileSync(resolve(__dirname, '../../openapi.json'), 'utf8')) as {
      paths: Record<string, { get: { parameters: { name: string }[] } }>
    }
    const names = spec.paths['/api/v1/trends/scans']!.get.parameters.map((p) => p.name)
    const own = ['cluster_id', 'as_of', 'days', 'interval']
    expect([...SCAN_FILTER_PARAMS].sort()).toEqual(names.filter((n) => !own.includes(n)).sort())
  })
})

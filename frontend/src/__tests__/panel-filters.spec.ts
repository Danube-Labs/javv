/**
 * The filters of a dashboard panel (issue 999): their words, the facets read that carries them,
 * and the Findings link of a click in a filtered panel.
 */
import { describe, expect, it } from 'vitest'

import type { ViewPreset } from '@/api/generated'
import { panelById } from '@/dashboards/catalog'
import {
  panelFilterFields,
  panelFilterParts,
  panelFiltersAt,
  panelFindingsQuery,
  panelQuery,
} from '@/dashboards/panelFilters'
import { FINDINGS_FIELDS } from '@/filters/fields.config'

const base = { cluster_id: 'c-k3d-0001' }
// a stored preset has `present: true` (the ViewPreset default); it is no filter of its own
const stored = (f: Record<string, unknown>) => ({ present: true, ...f }) as ViewPreset

describe('the words of the panel filters', () => {
  it('gives one text for each filter', () => {
    expect(panelFilterParts(stored({ exclude_namespace: ['kube-system'], kev: true }))).toEqual([
      'KEV',
      'Namespace is not kube-system',
    ])
  })

  it('gives none for no filters, an empty preset or a preset with only present', () => {
    expect(panelFilterParts(null)).toEqual([])
    expect(panelFilterParts(undefined)).toEqual([])
    expect(panelFilterParts({} as ViewPreset)).toEqual([])
    expect(panelFilterParts(stored({}))).toEqual([])
  })
})

describe('the facets read of a panel', () => {
  it('adds the filters and all_filters to the dashboard query', () => {
    expect(panelQuery({ ...base, as_of: '2026-10-01T00:00:00Z' }, stored({ exclude_namespace: ['kube-system'] }))).toEqual({
      cluster_id: 'c-k3d-0001',
      as_of: '2026-10-01T00:00:00Z',
      present: true,
      exclude_namespace: ['kube-system'],
      all_filters: true,
    })
  })

  it('leaves out a null param', () => {
    expect(panelQuery(base, stored({ severity: ['critical'], assignee: null }))).not.toHaveProperty('assignee')
  })

  it('keeps the dashboard query as it is for a panel with no filters, so the panels share a read', () => {
    expect(panelQuery(base, null)).toBe(base)
    expect(panelQuery(base, stored({}))).toBe(base)
  })
})

describe('the Findings link of a click in a filtered panel', () => {
  it('carries the panel filters with the value of the row', () => {
    expect(panelFindingsQuery(stored({ exclude_namespace: ['kube-system'] }), { severity: 'critical' })).toEqual({
      namespace: '!kube-system',
      severity: 'critical',
    })
  })

  it('lets the row value take the place of the panel filter on the same field', () => {
    expect(panelFindingsQuery(stored({ exclude_severity: ['low'] }), { severity: 'critical' })).toEqual({
      severity: 'critical',
    })
    expect(panelFindingsQuery(stored({ namespace: ['payments', 'edge'] }), { namespace: 'edge' })).toEqual({
      namespace: 'edge',
    })
  })

  it('keeps the flags of the panel and of the row', () => {
    expect(panelFindingsQuery(stored({ kev: true, fixable: true }), { attr: 'fixable' })).toEqual({
      attr: 'kev,fixable',
    })
    expect(panelFindingsQuery(stored({ kev: true }), { attr: 'disagree' })).toEqual({ attr: 'kev,disagree' })
  })

  it('gives the row query as it is for a panel with no filters', () => {
    expect(panelFindingsQuery(null, { ptype: 'npm' })).toEqual({ ptype: 'npm' })
    expect(panelFindingsQuery(undefined, {})).toEqual({})
  })
})

describe('"New in range" in a panel follows the dashboard range (operator, 2026-10-31)', () => {
  it('reads with the days of the dashboard range, not the stored days', () => {
    expect(panelFiltersAt(stored({ new_within_days: 7, kev: true }), 30)).toEqual(stored({ new_within_days: 30, kev: true }))
    // Last 24h is one day; a range is at most 365 days, as on Findings
    expect(panelFiltersAt(stored({ new_within_days: 7 }), 0.5)?.new_within_days).toBe(1)
    expect(panelFiltersAt(stored({ new_within_days: 7 }), 400)?.new_within_days).toBe(365)
  })

  it('leaves the other filters as they are, and gives null for no filters', () => {
    const f = stored({ exclude_namespace: ['kube-system'] })
    expect(panelFiltersAt(f, 30)).toEqual(f)
    expect(panelFiltersAt(null, 30)).toBeNull()
    expect(panelFiltersAt(undefined, 30)).toBeNull()
  })
})

describe('the fields of the Filters field in the panel settings', () => {
  const keys = (id: string) => panelFilterFields(panelById(id)!).map((f) => f.key)

  it('are the Findings fields less Scanner: the dashboard and the panel pick the scanner', () => {
    expect(keys('findings-by-namespace')).toEqual(FINDINGS_FIELDS.map((f) => f.key).filter((k) => k !== 'scanner'))
  })

  it('leave out the filters that a panel refuses: Triage progress splits by state itself', () => {
    expect(keys('triage-progress')).not.toContain('state')
    expect(keys('triage-progress')).not.toContain('scanner')
    expect(keys('findings-summary')).toContain('state')
  })
})

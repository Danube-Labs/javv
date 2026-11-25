/**
 * The filters of a dashboard panel (issue 999): their words, the facets read that carries them,
 * and the Findings link of a click in a filtered panel.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import type { ViewPreset } from '@/api/generated'
import { panelById } from '@/dashboards/catalog'
import { TRIAGE_ACTIONS } from '@/audit/fields.config'
import {
  PANEL_AUDIT_FIELDS,
  panelAuditFilterParts,
  panelAuditLogQuery,
  panelAuditQuery,
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
  const PAST = '2026-09-20T12:00:00Z'

  it('reads with the days of the dashboard range, not the stored days', () => {
    expect(panelFiltersAt(stored({ new_within_days: 7, kev: true }), 30, null)).toEqual({
      ...stored({ kev: true }),
      new_within_days: 30,
    })
    // a sub-day range at a past T is one day; a range is at most 365 days, as on Findings
    expect(panelFiltersAt(stored({ new_within_days: 7 }), 0.5, PAST)?.new_within_days).toBe(1)
    expect(panelFiltersAt(stored({ new_within_days: 7 }), 400, null)?.new_within_days).toBe(365)
  })

  it('a range of 2 days or less at now reads with its exact length, as on Findings (issue 1291)', () => {
    const f = panelFiltersAt(stored({ new_within_days: 7, kev: true }), 0.0417, null)
    expect(f?.new_within_seconds).toBe(3600)
    expect(f).not.toHaveProperty('new_within_days')
    expect(f?.kev).toBe(true)
    // a filter stored with seconds reads with the range of the dashboard too
    const back = panelFiltersAt(stored({ new_within_seconds: 3600 }), 7, null)
    expect(back?.new_within_days).toBe(7)
    expect(back).not.toHaveProperty('new_within_seconds')
  })

  it('leaves the other filters as they are, and gives null for no filters', () => {
    const f = stored({ exclude_namespace: ['kube-system'] })
    expect(panelFiltersAt(f, 30, null)).toEqual(f)
    expect(panelFiltersAt(null, 30, null)).toBeNull()
    expect(panelFiltersAt(undefined, 30, null)).toBeNull()
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

  it('leave out a refused flag and keep the other flags: New findings counts the new findings itself', () => {
    const flags = (id: string) => {
      const f = panelFilterFields(panelById(id)!).find((x) => x.key === 'attr')
      return f?.type === 'flags' ? f.values.map((v) => v.param) : []
    }
    const all = flags('findings-summary')
    expect(all).toContain('new_within_days')
    expect(flags('new-findings')).toEqual(all.filter((p) => p !== 'new_within_days'))
    expect(keys('new-findings')).toEqual(keys('findings-summary'))
  })

  it('are the filters that a scan record holds on Scan ingest, with No tag as its one flag (issue 1293)', () => {
    expect(keys('scan-ingest')).toEqual(['attr', 'namespace', 'image', 'tag', 'digest'])
    const attr = panelFilterFields(panelById('scan-ingest')!).find((f) => f.key === 'attr')
    expect(attr?.type === 'flags' ? attr.values.map((v) => v.param) : []).toEqual(['untagged'])
  })
})

/** Issue 1317 (D1, accepted on built pictures): the panel settings show Image and Tag as lists
 * with counts, from the facets read of the settings, as Namespace. */
describe('Image and Tag in the panel settings', () => {
  it.each(['findings-by-namespace', 'scan-ingest'])('are lists of the facets read on %s', (id) => {
    const fields = panelFilterFields(panelById(id)!)
    for (const [key, facetKey, param] of [
      ['image', 'image_repo', 'image_repo'],
      ['tag', 'tag', 'tag'],
    ] as const) {
      const f = fields.find((x) => x.key === key)
      expect(f).toMatchObject({ type: 'terms', facetKey, param, multi: true, negatable: true })
    }
  })

  it('say their values as a list does, with no quotes', () => {
    expect(
      panelFilterParts(stored({ image_repo: ['docker.io/library/postgres'], exclude_tag: ['latest', '13.4'] })),
    ).toEqual(['Image is docker.io/library/postgres', 'Tag is none of latest, 13.4'])
  })
})

describe('the audit filters of Triage activity (issue 1063)', () => {
  const triageBase = { cluster_id: 'c-k3d-0001', entity_type: ['finding', 'decision'] }

  it('are Action and User: the panel sets Entity itself', () => {
    expect(PANEL_AUDIT_FIELDS.map((f) => f.key)).toEqual(['action', 'actor'])
  })

  it('list only the triage actions, since the panel counts only finding and decision rows', () => {
    const action = PANEL_AUDIT_FIELDS.find((f) => f.key === 'action')!
    expect(action.type === 'terms' && action.values).toEqual([...TRIAGE_ACTIONS])
    expect(TRIAGE_ACTIONS).toContain('risk_accept')
    expect(TRIAGE_ACTIONS).toContain('decision_revoke')
    expect(TRIAGE_ACTIONS).not.toContain('login')
    expect(TRIAGE_ACTIONS).not.toContain('dashboard_update')
  })

  it('are the triage actions that the backend stores on a panel, no more and no fewer', () => {
    const source = readFileSync(resolve(process.cwd(), '..', 'backend/src/backend/query/contributors.py'), 'utf8')
    const block = /^TRIAGE_ACTIONS = frozenset\(([\s\S]*?)^\)/m.exec(source)?.[1] ?? ''
    const backend = [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1])
    expect(backend.length).toBeGreaterThan(0)
    expect([...backend].sort()).toEqual([...TRIAGE_ACTIONS].sort())
  })

  it('give one text for each filter, with the words of the Audit log', () => {
    expect(panelAuditFilterParts({ action: ['risk_accept', 'not_affected'], exclude_actor: ['bot'] })).toEqual([
      'Action is one of Risk accepted, Not affected',
      'User is not bot',
    ])
    expect(panelAuditFilterParts(null)).toEqual([])
    expect(panelAuditFilterParts({})).toEqual([])
  })

  it('go into the read of the panel, and leave a null param out', () => {
    expect(panelAuditQuery(triageBase, { action: ['resolve'], actor: null })).toEqual({
      ...triageBase,
      action: ['resolve'],
    })
  })

  it('keep the query of the panel as it is when there are none', () => {
    expect(panelAuditQuery(triageBase, null)).toBe(triageBase)
    expect(panelAuditQuery(triageBase, {})).toBe(triageBase)
  })

  it('open the Audit log with the same filters and the entities that the panel counts', () => {
    expect(panelAuditLogQuery({ action: ['risk_accept'], exclude_actor: ['bot'] })).toEqual({
      entity: 'finding,decision',
      action: 'risk_accept',
      actor: '!bot',
    })
    expect(panelAuditLogQuery(null)).toEqual({ entity: 'finding,decision' })
  })
})

// The Digest filter (issue 1140) is one more Findings field: a panel stores it as image_digest,
// reads with it, says it in words and carries it to Findings.
describe('the Digest filter in a panel', () => {
  const f = stored({ image_digest: 'sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1' })
  it('says it in words, as the other text fields do', () => {
    expect(panelFilterParts(f)).toEqual(['Digest "sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1"'])
  })
  it('reads with it', () => {
    expect(panelQuery(base, f)).toMatchObject({ image_digest: 'sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1', all_filters: true })
  })
  it('carries it to Findings with the value of the row', () => {
    expect(panelFindingsQuery(f, { severity: 'critical' })).toEqual({ digest: 'sha256:1adb50e5c24f550a9e68457a2ce60e9e4103dfc43c3b36e98310168165b443a1', severity: 'critical' })
  })
})

/**
 * A settings change or a job run keeps its values only as JSON. Its line in the Audit log and the
 * Contributors feed names the values that changed, with the names and units of the screen that
 * sets them (issue 933).
 */
import { readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { auditDetail, feedDetail } from '@/audit/auditDetail'
import { JSON_KEYS, NOT_SHOWN, jsonChange } from '@/audit/jsonChange'

const BACKEND = resolve(process.cwd(), '..', 'backend/src/backend')
const source = (path: string): string => readFileSync(join(BACKEND, path), 'utf8')

/** the fields of a pydantic model, read from its class body (docstrings left out) */
function modelFields(path: string, model: string): string[] {
  const text = source(path)
  const start = text.indexOf(`class ${model}(`)
  expect(start).toBeGreaterThan(-1)
  const rest = text.slice(start).split('\n').slice(1)
  const end = rest.findIndex((line) => /^\S/.test(line))
  const body = rest.slice(0, end).join('\n').replace(/"""[\s\S]*?"""/g, '')
  return [...body.matchAll(/^ {4}(\w+): /gm)].map((m) => m[1]!).filter((f) => f !== 'model_config')
}

/** the keys a job writes on its audit row: the JSON of its audit call, and the counts it spreads */
function jobKeys(path: string): string[] {
  const text = source(path)
  const call = text.slice(text.indexOf('append_field_change('))
  const json = /new_value_json=\{([^}]*)\}/.exec(call)![1]!
  const keys = [...json.matchAll(/"(\w+)":/g)].map((m) => m[1]!)
  if (json.includes('**counts')) {
    const counts = /\bcounts = \{([^}]*)\}/.exec(text)![1]!
    keys.push(...[...counts.matchAll(/"(\w+)":/g)].map((m) => m[1]!))
  }
  return keys
}

describe('every JSON value the backend writes on an audit row has a name', () => {
  const models: [string, string, string][] = [
    ['sla_policy', 'sla/policy.py', 'SlaPolicy'],
    ['staleness_timers', 'jobs/staleness.py', 'StalenessTimers'],
    ['scan_scope', 'admin/scan_scope.py', 'ScanScope'],
    ['retirement_window', 'admin/cluster_retirement.py', 'RetirementWindow'],
    ['rollover', 'jobs/lifecycle.py', 'LifecycleSettings'],
  ]
  it.each(models)('%s: each field of the model', (field, path, model) => {
    const fields = modelFields(path, model)
    expect(fields.length).toBeGreaterThan(1)
    expect(fields.filter((f) => !(f in JSON_KEYS[field]!))).toEqual([])
  })

  it('counts: each key of the two job rows', () => {
    const keys = [...jobKeys('jobs/findings_cleanup.py'), ...jobKeys('jobs/session_sweep.py')]
    // the reader works: it finds a key of each job
    expect(keys).toContain('watermarks_pruned')
    expect(keys).toContain('sessions_deleted')
    expect(keys.filter((k) => !(k in JSON_KEYS['counts']!) && !NOT_SHOWN.has(k))).toEqual([])
  })
})

const SLA = { critical_days: 2, high_days: 7, medium_days: 30, low_days: 90, kev_days: 1 }

describe('jsonChange', () => {
  it('a change shows only the values that changed, with the unit once', () => {
    expect(jsonChange('sla_policy', SLA, { ...SLA, critical_days: 7, kev_days: 0.5 })).toBe(
      'SLA policy: Critical 2 → 7 days · KEV override 1 → 0.5 days',
    )
  })

  it('a save with the same values says no change', () => {
    expect(jsonChange('staleness_timers', { freshness_days: 3, scanner_down_days: 7 }, { freshness_days: 3, scanner_down_days: 7 })).toBe(
      'Staleness timers: no change',
    )
  })

  it('a list shows its items, and an empty list shows none', () => {
    const before = { include_namespaces: [], ignore_namespaces: ['kube-system'], exclude_images: [], ignore_kinds: [] }
    const after = { ...before, ignore_namespaces: ['kube-system', 'monitoring'], ignore_kinds: ['Job'] }
    expect(jsonChange('scan_scope', before, after)).toBe(
      'Scan scope: Ignored namespaces kube-system → kube-system, monitoring · Skip workload kinds none → Job',
    )
  })

  it('a retirement window of null reads as Never', () => {
    expect(jsonChange('retirement_window', { retire_after_days: 30, warn_days: 7 }, { retire_after_days: null, warn_days: 7 })).toBe(
      'Cluster retirement: Retire a silent cluster 30 days → Never',
    )
  })

  it('a row with no old values shows all its values, and leaves out the per-cluster counts', () => {
    expect(
      jsonChange('counts', null, { findings_deleted: 0, watermarks_pruned: 3, by_cluster: { c1: { findings_deleted: 0 } } }),
    ).toBe('Counts: Findings deleted 0 · Watermarks pruned 3')
    expect(jsonChange('counts', undefined, { sessions_deleted: 15096, grace_hours: 24 })).toBe(
      'Counts: Sessions deleted 15096 · Grace period 24 hours',
    )
  })

  it('a key with no name reads as its words', () => {
    expect(jsonChange('rollover', { max_docs: 5, new_knob: 1 }, { max_docs: 5, new_knob: 2 })).toBe('Rollover thresholds: new knob 1 → 2')
  })

  it('a row with nothing to show adds nothing', () => {
    expect(jsonChange('counts', null, {})).toBe('')
  })
})

describe('the Audit log and the feed use it for JSON-only rows', () => {
  const sla = {
    action: 'sla_policy_change',
    field: 'sla_policy',
    old_value: null,
    new_value: null,
    old_value_json: SLA,
    new_value_json: { ...SLA, critical_days: 7 },
  }

  it('the Audit log and the feed show the same line', () => {
    expect(auditDetail(sla)).toBe('SLA policy: Critical 2 → 7 days')
    expect(feedDetail(sla)).toBe('SLA policy: Critical 2 → 7 days')
  })

  it('a bulk change keeps its own line', () => {
    const bulk = {
      action: 'bulk_triage',
      field: 'bulk_patch',
      new_value_json: { patch: { state: 'acknowledged' }, result_count: 2, target_ids: ['a', 'b'] },
    }
    expect(auditDetail(bulk)).toBe('State → Acknowledged: 2 findings (frozen set)')
    expect(feedDetail(bulk)).toBe('Bulk change → updated')
  })
})

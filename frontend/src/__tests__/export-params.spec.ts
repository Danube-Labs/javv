import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { EXPORT_PARAM_KEYS, scheduleParams, unrepresentableKeys } from '@/findings/exportParams'

// a full findings lens the way buildFilterQuery emits it
const LENS = {
  cluster_id: 'c-1',
  as_of: '2026-07-08T23:59:59.999Z',
  q: 'openssl',
  severity: ['critical', 'high'],
  state: ['open', 'stale'],
  scanner: 'trivy',
  assignee: 'alice',
  kev: true,
  fixable: true,
  disagree: true,
  overdue: true,
  new_within_days: 30,
  namespace: 'payments',
  ptype: 'deb',
  image_repo: 'nginx',
}

describe('scheduleParams (audit F-07 — the whole lens rides the schedule)', () => {
  it('copies every ExportParams field and drops only the globals', () => {
    const params = scheduleParams(LENS, 'csv', 'trivy')
    const { cluster_id: _c, as_of: _t, ...lensParams } = LENS
    expect(params).toEqual({ format: 'csv', ...lensParams }) // globals ride the body, not params
    expect(EXPORT_PARAM_KEYS).toEqual(expect.arrayContaining(Object.keys(lensParams)))
  })

  it('previously-dropped filters are carried now (the F-07 offenders)', () => {
    const params = scheduleParams(LENS, 'csv', 'trivy')
    for (const key of ['q', 'overdue', 'new_within_days', 'namespace', 'ptype'] as const) {
      expect(params[key]).toEqual(LENS[key])
    }
  })

  it('VEX pins its single scanner over the lens value (per-scanner sacred)', () => {
    const params = scheduleParams({ ...LENS, scanner: 'trivy' }, 'vex', 'grype')
    expect(params.format).toBe('openvex')
    expect(params.scanner).toBe('grype')
  })
})

describe('unrepresentableKeys (block loudly, never widen silently)', () => {
  it('a full known lens has no offenders', () => {
    expect(unrepresentableKeys(LENS)).toEqual([])
  })

  it('a future lens key the contract lacks blocks by name', () => {
    expect(unrepresentableKeys({ ...LENS, some_new_dim: 'x' })).toEqual(['some_new_dim'])
  })
})

describe('EXPORT_PARAM_KEYS and the backend contract (issue 962)', () => {
  it('has every ExportParams field of openapi.json except format, and nothing else', () => {
    const openapi = JSON.parse(readFileSync(resolve(process.cwd(), 'openapi.json'), 'utf8'))
    const backend = Object.keys(openapi.components.schemas.ExportParams.properties)
      .filter((k) => k !== 'format')
      .sort()
    expect([...EXPORT_PARAM_KEYS].sort()).toEqual(backend)
  })

  it('a lens with the four filters it used to refuse can be scheduled', () => {
    const lens = {
      cluster_id: 'c-1',
      package_name: ['openssl'],
      exclude_package_name: ['zlib'],
      exclude_cve_id: ['CVE-2021-3711'],
      unassigned: true,
    }
    expect(unrepresentableKeys(lens)).toEqual([])
    const { cluster_id: _c, ...lensParams } = lens
    expect(scheduleParams(lens, 'csv', 'trivy')).toEqual({ format: 'csv', ...lensParams })
  })
})

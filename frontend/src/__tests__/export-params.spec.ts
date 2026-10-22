import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import { FINDINGS_FIELDS, type FilterField } from '@/filters/fields.config'
import {
  EXPORT_PARAM_KEYS,
  type ExportChoice,
  PAST_TIME_UNRECORDED_KEYS,
  exportBlockMessage,
  filterNames,
  scheduleParams,
  unrepresentableKeys,
} from '@/findings/exportParams'

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

  it('the four filters it used to refuse can be scheduled', () => {
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

const SCHEDULE: ExportChoice = { schedule: true, historical: false, format: 'csv', vexScanner: 'trivy' }
const RUN_NOW: ExportChoice = { ...SCHEDULE, schedule: false }
const block = (query: Record<string, unknown>, choice: ExportChoice = SCHEDULE) =>
  exportBlockMessage(FINDINGS_FIELDS, { cluster_id: 'c-1', ...query }, choice)

describe('the block message names filters as the screen does (issue 962)', () => {
  it('a field gives its label, an exclude key its field label, a flag its label', () => {
    expect(
      filterNames(FINDINGS_FIELDS, ['package_name', 'exclude_cve_id', 'unassigned', 'some_new_dim']),
    ).toEqual(['Package', 'CVE', 'Unassigned', 'some_new_dim'])
  })

  it('a filter the schedule lacks is named by its label', () => {
    const fields: FilterField[] = [
      ...FINDINGS_FIELDS,
      { key: 'base', label: 'Base image', type: 'text', param: 'base_image' },
    ]
    const query = { cluster_id: 'c-1', base_image: 'alpine' }
    expect(exportBlockMessage(fields, query, SCHEDULE)).toBe(
      'A schedule cannot use these filters: Base image. Clear them, or use Run now.',
    )
    // at a past time Run now is not offered
    expect(exportBlockMessage(fields, query, { ...SCHEDULE, historical: true })).toBe(
      'A schedule cannot use these filters: Base image. Clear them.',
    )
  })

  it('nothing blocks the filters a schedule can carry', () => {
    expect(block(LENS)).toBeNull()
    expect(block({ unassigned: true })).toBeNull()
    expect(block({ exclude_assignee: ['bob'], unassigned: true })).toBeNull()
  })
})

describe('Assignee with Unassigned, which Findings and the schedule refuse', () => {
  it('blocks Run now and the schedule alike', () => {
    const message = 'An export cannot use Assignee and Unassigned together. Clear one of them.'
    expect(block({ assignee: ['bob'], unassigned: true })).toBe(message)
    expect(block({ assignee: ['bob'], unassigned: true }, RUN_NOW)).toBe(message)
  })
})

describe('a VEX file covers the one scanner the screen shows', () => {
  const vex = (vexScanner: string, schedule = true): ExportChoice => ({ ...SCHEDULE, format: 'vex', vexScanner, schedule })

  it('Scanner is not X blocks VEX on both tabs, and CSV keeps it', () => {
    const message = 'A VEX file covers one scanner. Clear the Scanner filter first.'
    expect(block({ exclude_scanner: 'trivy' }, vex('grype'))).toBe(message)
    expect(block({ exclude_scanner: 'trivy' }, vex('grype', false))).toBe(message)
    expect(block({ exclude_scanner: 'trivy' })).toBeNull()
  })

  it('a VEX scanner other than the screen scanner blocks, the same one passes', () => {
    expect(block({ scanner: 'trivy' }, vex('grype'))).toBe(
      'This screen shows trivy findings only. Pick trivy for the VEX file.',
    )
    expect(block({ scanner: 'trivy' }, vex('grype', false))).not.toBeNull()
    expect(block({ scanner: 'trivy' }, vex('trivy'))).toBeNull()
    expect(block({}, vex('grype'))).toBeNull()
  })
})

describe('a schedule at a past time', () => {
  const PAST: ExportChoice = { ...SCHEDULE, historical: true }

  it('names each filter the scan history does not record', () => {
    expect(block({ q: 'openssl', kev: true, image_repo: ['nginx'] }, PAST)).toBe(
      'At a past time, a schedule cannot use these filters: KEV, Image, Search. Clear them.',
    )
    expect(block({ new_within_days: 30, disagree: true }, PAST)).toBe(
      'At a past time, a schedule cannot use these filters: Scanners disagree, New in range. Clear them.',
    )
  })

  it('takes the filters the history records, and the same filters now', () => {
    expect(block({ severity: ['high'], package_name: ['openssl'], unassigned: true }, PAST)).toBeNull()
    expect(block({ q: 'openssl', kev: true })).toBeNull()
  })

  it('the list equals the filters the backend refuses at a past time', () => {
    const reader = readFileSync(resolve(process.cwd(), '../backend/src/backend/query/as_of_t.py'), 'utf8')
    const backend = [...reader.matchAll(/_unrecorded\("(\w+)"\)/g)].map((m) => m[1]).sort()
    expect(backend.length).toBeGreaterThan(0)
    expect([...PAST_TIME_UNRECORDED_KEYS].sort()).toEqual(backend)
  })
})

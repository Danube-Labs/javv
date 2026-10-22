/**
 * M9d slice 1 units: causal display order (D38/H8 + D40/H-r3 — same-field edits replay by
 * `revision`, never arrival order) and the audit screen's emitted query params (the shared
 * builder over AUDIT_FIELDS — cluster_id always on, single-value terms, as_of pass-through).
 */
import { describe, expect, it } from 'vitest'

import { causalOrder } from '@/audit/causalOrder'
import { AUDIT_FIELDS } from '@/audit/fields.config'
import { buildFilterQuery } from '@/filters/buildFilterQuery'

const ev = (over: Record<string, unknown>) => ({
  '@timestamp': '2026-07-11T10:00:00.000000+00:00',
  event_id: 'e-x',
  entity_id: 'fk-1',
  field: 'state',
  revision: 1,
  ...over,
})

describe('causalOrder', () => {
  it('golden: interleaved same-field edits in one millisecond replay by revision', () => {
    // a CAS retry landed three rows for the same (entity, field) with shuffled event_ids —
    // the wire tiebreak (event_id) would replay old→new→old; revision is the truth
    const page = [
      ev({ event_id: 'e-c', revision: 2, old_value: 'open', new_value: 'acknowledged' }),
      ev({ event_id: 'e-a', revision: 3, old_value: 'acknowledged', new_value: 'resolved' }),
      ev({ event_id: 'e-b', revision: 1, old_value: null, new_value: 'open' }),
    ]
    expect(causalOrder(page, 'desc').map((e) => e.revision)).toEqual([3, 2, 1])
    expect(causalOrder(page, 'asc').map((e) => e.revision)).toEqual([1, 2, 3])
  })

  it('different fields/entities keep the wire (@timestamp, event_id) order', () => {
    const page = [
      ev({ event_id: 'e-b', field: 'assignee', revision: 9 }),
      ev({ event_id: 'e-a', field: 'state', revision: 1 }),
      ev({ '@timestamp': '2026-07-11T09:00:00.000000+00:00', event_id: 'e-z', revision: 5 }),
    ]
    expect(causalOrder(page, 'desc').map((e) => e.event_id)).toEqual(['e-b', 'e-a', 'e-z'])
  })

  it('rows without a revision (auth events) never trip the causal branch', () => {
    const page = [
      ev({ event_id: 'e-b', field: null, revision: null }),
      ev({ event_id: 'e-a', field: null, revision: null }),
    ]
    expect(causalOrder(page, 'desc').map((e) => e.event_id)).toEqual(['e-b', 'e-a'])
  })
})

describe('audit query params', () => {
  const sel = (over: Record<string, string[]> = {}) => ({ entity: [], action: [], actor: [], ...over })

  it('cluster_id is always on; each field sends its values as a list (issue 952)', () => {
    const q = buildFilterQuery(
      AUDIT_FIELDS,
      sel({ entity: ['finding'], action: ['resolve'], actor: ['admin'] }),
      { cluster_id: 'c-1' },
    )
    expect(q).toEqual({ cluster_id: 'c-1', entity_type: ['finding'], action: ['resolve'], actor: ['admin'] })
  })

  it('as_of rides only when time-traveling (D28)', () => {
    expect(buildFilterQuery(AUDIT_FIELDS, sel(), { cluster_id: 'c-1' })).toEqual({ cluster_id: 'c-1' })
    expect(
      buildFilterQuery(AUDIT_FIELDS, sel(), { cluster_id: 'c-1', as_of: '2026-07-10T00:00:00+00:00' }),
    ).toEqual({ cluster_id: 'c-1', as_of: '2026-07-10T00:00:00+00:00' })
  })
})

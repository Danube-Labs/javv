/**
 * The payload of a bulk-triage audit row (issue 912): the Audit table and a finding's Activity
 * card read the same shape, so one helper reads it.
 */
import { describe, expect, it } from 'vitest'

import { bulkChange, bulkJson } from '@/audit/bulkAudit'

const bulkRow = (patch: Record<string, unknown>) => ({
  action: 'bulk_triage',
  new_value_json: { patch, target_ids: ['fk-1', 'fk-2'], result_count: 2, result_hash: 'h' },
})

describe('bulkJson', () => {
  it('reads the payload of a bulk row', () => {
    expect(bulkJson(bulkRow({ state: 'acknowledged' }))).toMatchObject({ result_count: 2 })
  })

  it('is null for any other row, and for a bulk row with no payload', () => {
    expect(bulkJson({ action: 'acknowledge', new_value_json: { patch: {} } })).toBeNull()
    expect(bulkJson({ action: 'bulk_triage', new_value_json: null })).toBeNull()
    expect(bulkJson({ action: 'bulk_triage' })).toBeNull()
  })
})

describe('bulkChange', () => {
  it('names the state, the assignee and the note that the bulk change set', () => {
    expect(bulkChange(bulkRow({ state: 'acknowledged', assignee: 'bob', notes: 'Low risk' }))).toEqual({
      state: 'acknowledged',
      assignee: 'bob',
      notes: 'Low risk',
    })
  })

  it('leaves out what the bulk change did not set', () => {
    expect(bulkChange(bulkRow({ notes: 'Checked' }))).toEqual({ state: null, assignee: null, notes: 'Checked' })
  })

  it('is null for a row that is not a bulk change', () => {
    expect(bulkChange({ action: 'acknowledge' })).toBeNull()
  })
})

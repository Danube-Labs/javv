/**
 * The one-line text of an audit change in the Audit log and the Contributors feed (issue 931):
 * the field by its plain name, a state or a reason by its label. The layout of the line does not
 * change.
 */
import { describe, expect, it } from 'vitest'

import { auditDetail, feedDetail } from '@/audit/auditDetail'

const row = (r: Record<string, unknown>) => ({ action: 'x', ...r })

describe('auditDetail, the Detail column of the Audit log', () => {
  it('a state change shows both states by their labels', () => {
    expect(auditDetail(row({ field: 'state', old_value: 'open', new_value: 'not_affected' }))).toBe(
      'State: Open → Not affected',
    )
  })

  it('a change to Not affected shows the reason that came with it', () => {
    expect(
      auditDetail(
        row({
          field: 'state',
          old_value: 'open',
          new_value: 'not_affected',
          new_value_json: { vex_justification: 'component_not_present' },
        }),
      ),
    ).toBe('State: Open → Not affected · Reason: Component not present')
  })

  it('a state change with no reason, or other JSON, shows the states only', () => {
    expect(auditDetail(row({ field: 'state', old_value: 'not_affected', new_value: 'open', new_value_json: null }))).toBe(
      'State: Not affected → Open',
    )
    expect(
      auditDetail(row({ field: 'state', old_value: 'open', new_value: 'risk_accepted', new_value_json: { expires: 'x' } })),
    ).toBe('State: Open → Risk accepted')
  })

  it('a settings value that the backend wrote as a float shows as a whole number', () => {
    expect(auditDetail(row({ field: 'retention_days', old_value: '90', new_value: '105.0' }))).toBe(
      'History retention: 90 → 105',
    )
  })

  it('a change of reason shows both reasons by their labels', () => {
    expect(
      auditDetail(
        row({ field: 'vex_justification', old_value: 'component_not_present', new_value: 'vulnerable_code_not_present' }),
      ),
    ).toBe('Reason: Component not present → Vulnerable code not present')
  })

  it('a first value and a cleared value keep their words', () => {
    expect(auditDetail(row({ field: 'assignee', old_value: null, new_value: 'alice' }))).toBe('Assigned to: alice')
    expect(auditDetail(row({ field: 'assignee', old_value: 'alice', new_value: null }))).toBe('Assigned to: alice cleared')
  })

  it('a settings value shows as it is, after the name of its setting', () => {
    expect(auditDetail(row({ field: 'retention_days', old_value: '30', new_value: '60' }))).toBe('History retention: 30 → 60')
  })

  it('a row with no field or no value adds nothing', () => {
    expect(auditDetail(row({}))).toBe('')
    expect(auditDetail(row({ field: 'sla_policy', old_value: null, new_value: null }))).toBe('')
  })

  it('a bulk change names each field it set, and the count', () => {
    expect(
      auditDetail({
        action: 'bulk_triage',
        field: 'bulk_patch',
        new_value_json: {
          patch: { state: 'not_affected', vex_justification: 'component_not_present', notes: 'Not shipped' },
          result_count: 3,
        },
      }),
    ).toBe('State → Not affected · Reason → Component not present · Note → Not shipped: 3 findings (frozen set)')
  })
})

describe('feedDetail, the detail line of the Contributors feed', () => {
  it('names the field and the new value by their labels', () => {
    expect(feedDetail(row({ field: 'state', new_value: 'risk_accepted' }))).toBe('State → Risk accepted')
    expect(feedDetail(row({ field: 'vex_justification', new_value: 'inline_mitigations_already_exist' }))).toBe(
      'Reason → Inline mitigations exist',
    )
  })

  it('a change kept as JSON reads as updated, and no value as the empty sign', () => {
    expect(feedDetail(row({ field: 'sla_policy', new_value: null, new_value_json: { critical: 7 } }))).toBe(
      'SLA policy → updated',
    )
    expect(feedDetail(row({ field: 'assignee', new_value: null }))).toBe('Assigned to → ∅')
  })

  it('a row with no field adds nothing', () => {
    expect(feedDetail(row({}))).toBe('')
  })
})

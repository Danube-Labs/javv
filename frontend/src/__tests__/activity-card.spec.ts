/**
 * A finding's Activity card: each row names its action with the Audit log's action pill
 * (issue 918), and a bulk change that included the finding shows the state and the note that
 * it set (issue 912).
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ActivityCard, { type ActivityRow } from '@/components/finding/ActivityCard.vue'

const at = '2026-10-18T10:00:00Z'

function rowOf(row: ActivityRow) {
  return mount(ActivityCard, { props: { activity: [row] } }).find('.act-row')
}

describe('ActivityCard', () => {
  it('a bulk change shows its action pill, its state and its note', () => {
    const row = rowOf({
      event_id: 'e-1',
      action: 'bulk_triage',
      actor: 'lead',
      field: 'bulk_patch',
      new_value: null,
      new_value_json: { patch: { state: 'acknowledged', notes: 'Low risk' }, target_ids: ['fk-1'] },
      '@timestamp': at,
    })
    expect(row.text()).toContain('lead')
    expect(row.find('.action-tag').text()).toBe('Bulk triage')
    expect(row.text()).not.toContain('bulk_triage')
    expect(row.find('.state-tag').text()).toContain('Acknowledged')
    expect(row.text()).toContain('Note: Low risk')
    expect(row.text()).not.toContain('notes:')
  })

  it('a bulk change to Not affected also shows its reason', () => {
    const row = rowOf({
      event_id: 'e-8',
      action: 'bulk_triage',
      actor: 'lead',
      field: 'bulk_patch',
      new_value: null,
      new_value_json: {
        patch: { state: 'not_affected', vex_justification: 'component_not_present' },
        target_ids: ['fk-1'],
      },
      '@timestamp': at,
    })
    expect(row.find('.state-tag').text()).toContain('Not affected')
    expect(row.text()).toContain('Reason: Component not present')
    expect(row.text()).not.toContain('component_not_present')
  })

  it('a single state change names the state once, in the action pill', () => {
    const row = rowOf({
      event_id: 'e-2',
      action: 'acknowledge',
      actor: 'lead',
      field: 'state',
      new_value: 'acknowledged',
      '@timestamp': at,
    })
    expect(row.find('.action-tag').text()).toBe('Acknowledged')
    expect(row.find('.action-tag').attributes('data-tone')).toBe('ack')
    expect(row.find('.state-tag').exists()).toBe(false)
    expect(row.text()).not.toContain('state:')
  })

  it('a change to Not affected shows the reason that came with it', () => {
    const row = rowOf({
      event_id: 'e-9',
      action: 'not_affected',
      actor: 'lead',
      field: 'state',
      old_value: 'open',
      new_value: 'not_affected',
      new_value_json: { vex_justification: 'vulnerable_code_not_in_execute_path' },
      '@timestamp': at,
    })
    expect(row.find('.action-tag').text()).toBe('Not affected')
    expect(row.find('.act-part').text()).toBe('· Reason: Code not in execute path')
    expect(row.find('.state-tag').exists()).toBe(false)
  })

  it('an assignee change shows the Assigned pill and the new assignee', () => {
    const row = rowOf({
      event_id: 'e-3',
      action: 'assign',
      actor: 'lead',
      field: 'assignee',
      new_value: 'alice',
      '@timestamp': at,
    })
    expect(row.find('.action-tag').text()).toBe('Assigned')
    expect(row.find('.act-part').text()).toBe('· Assigned to: alice')
  })

  it('a note keeps its label and its text in one part, so a long note wraps as one piece', () => {
    const row = rowOf({
      event_id: 'e-5',
      action: 'note',
      actor: 'lead',
      field: 'notes',
      new_value: 'Fix ships with the next base image',
      '@timestamp': at,
    })
    expect(row.find('.action-tag').text()).toBe('Note')
    expect(row.find('.act-part').text()).toBe('· Note: Fix ships with the next base image')
  })

  it('a new reason on a Not affected finding reads as the plain label of the triage panel', () => {
    const row = rowOf({
      event_id: 'e-6',
      action: 'not_affected',
      actor: 'lead',
      field: 'vex_justification',
      old_value: 'vulnerable_code_not_present',
      new_value: 'component_not_present',
      '@timestamp': at,
    })
    expect(row.find('.action-tag').text()).toBe('Not affected')
    expect(row.find('.act-part').text()).toBe('· Reason: Component not present')
    expect(row.text()).not.toContain('vex_justification')
    expect(row.text()).not.toContain('component_not_present')
    expect(row.find('.act-part .mono-cell').exists()).toBe(false)
  })

  it('a reason that is not one of the five shows its value as it is', () => {
    const row = rowOf({
      event_id: 'e-7',
      action: 'not_affected',
      actor: 'lead',
      field: 'vex_justification',
      new_value: 'some_future_reason',
      '@timestamp': at,
    })
    expect(row.find('.act-part').text()).toBe('· Reason: some_future_reason')
  })

  it('an action with no label reads as words, never as snake_case', () => {
    const row = rowOf({ event_id: 'e-4', action: 'some_future_action', actor: 'lead', '@timestamp': at })
    expect(row.find('.action-tag').text()).toBe('some future action')
  })
})

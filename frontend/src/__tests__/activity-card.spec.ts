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
    expect(row.text()).toContain('notes: Low risk')
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
    expect(row.text()).toContain('assignee: alice')
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
    expect(row.find('.act-part').text()).toBe('· notes: Fix ships with the next base image')
  })

  it('an action with no label reads as words, never as snake_case', () => {
    const row = rowOf({ event_id: 'e-4', action: 'store_inspect', actor: 'lead', '@timestamp': at })
    expect(row.find('.action-tag').text()).toBe('store inspect')
  })
})

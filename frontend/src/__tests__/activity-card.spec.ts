/**
 * A finding's Activity card (issue 912): a bulk change that included the finding shows like a
 * single change, with the state and the note that it set.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ActivityCard, { type ActivityRow } from '@/components/finding/ActivityCard.vue'

const at = '2026-10-18T10:00:00Z'

describe('ActivityCard', () => {
  it('a bulk change shows its state and its note', () => {
    const rows: ActivityRow[] = [
      {
        event_id: 'e-1',
        action: 'bulk_triage',
        actor: 'lead',
        field: 'bulk_patch',
        new_value: null,
        new_value_json: { patch: { state: 'acknowledged', notes: 'Low risk' }, target_ids: ['fk-1'] },
        '@timestamp': at,
      },
    ]
    const w = mount(ActivityCard, { props: { activity: rows } })
    const row = w.find('.act-row')
    expect(row.text()).toContain('lead')
    expect(row.text()).toContain('bulk_triage')
    expect(row.find('.state-tag').exists()).toBe(true)
    expect(row.find('.state-tag').text()).toContain('Acknowledged')
    expect(row.text()).toContain('notes: Low risk')
  })

  it('a single change still shows its state', () => {
    const rows: ActivityRow[] = [
      { event_id: 'e-2', action: 'acknowledge', actor: 'lead', field: 'state', new_value: 'acknowledged', '@timestamp': at },
    ]
    const w = mount(ActivityCard, { props: { activity: rows } })
    expect(w.find('.act-row .state-tag').text()).toContain('Acknowledged')
  })
})

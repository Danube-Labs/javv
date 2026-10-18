/**
 * The Audit table's line for a bulk change (issue 912): it reads the payload through the shared
 * `bulkJson`, and says what the change set and how many findings it covered.
 */
import { mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { describe, expect, it } from 'vitest'

import AuditTable from '@/components/audit/AuditTable.vue'
import type { AuditEvent } from '@/stores/audit'

describe('AuditTable, a bulk change', () => {
  it('shows the patch and the count of findings', () => {
    const row: AuditEvent = {
      event_id: 'e-1',
      '@timestamp': '2026-10-18T10:00:00Z',
      actor: 'lead',
      action: 'bulk_triage',
      entity_type: 'finding',
      entity_id: 'bulk:abc',
      field: 'bulk_patch',
      new_value_json: { patch: { state: 'acknowledged' }, target_ids: ['fk-1', 'fk-2'], result_count: 2 },
    }
    const w = mount(AuditTable, {
      props: { rows: [row] },
      global: { plugins: [[PrimeVue, { unstyled: true }]], stubs: { RouterLink: true } },
    })
    expect(w.text()).toContain('state → acknowledged: 2 findings (frozen set)')
  })
})

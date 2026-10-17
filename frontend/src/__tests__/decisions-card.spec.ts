/**
 * The decisions card per role (issue 892, ruling 2 as changed to option 1, and ruling 5): "New
 * decision" makes a risk-accept, so only can_accept_audit_final sees it; a triager revokes a
 * not-affected decision but never a risk-accept or an ignore rule; an ignore rule wears the
 * "Risk accepted" tag, because that is the state it gives the finding.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import DecisionsCard, { type DecisionRow } from '@/components/triage/DecisionsCard.vue'

const decisions: DecisionRow[] = [
  { decision_id: 'd-na', type: 'not_affected', created_by: 'tri' },
  { decision_id: 'd-ra', type: 'risk_accepted', created_by: 'lead' },
  { decision_id: 'd-ir', type: 'ignore_rule', created_by: 'lead' },
  { decision_id: 'd-gone', type: 'not_affected', created_by: 'tri', revoked_at: '2026-10-01T00:00:00Z' },
]

function card(canTriage: boolean, canAcceptFinal: boolean) {
  return mount(DecisionsCard, { props: { decisions, canTriage, canAcceptFinal, busy: false } })
}

/** The decision id of each row that offers Revoke, read from the emitted event. */
async function revocable(w: ReturnType<typeof card>): Promise<string[]> {
  for (const button of w.findAll('button').filter((b) => b.text() === 'Revoke')) await button.trigger('click')
  return (w.emitted('revoke') ?? []).map(([id]) => id as string)
}

const hasNewDecision = (w: ReturnType<typeof card>) => w.findAll('button').some((b) => b.text().includes('New decision'))

describe('the decisions card per role', () => {
  it('a viewer gets no button', async () => {
    const w = card(false, false)
    expect(hasNewDecision(w)).toBe(false)
    expect(await revocable(w)).toEqual([])
  })

  it('a triager revokes a not-affected decision only, and gets no New decision', async () => {
    const w = card(true, false)
    expect(hasNewDecision(w)).toBe(false)
    expect(await revocable(w)).toEqual(['d-na'])
  })

  it('a lead revokes each active decision and gets New decision', async () => {
    const w = card(true, true)
    expect(hasNewDecision(w)).toBe(true)
    expect(await revocable(w)).toEqual(['d-na', 'd-ra', 'd-ir'])
  })

  it('shows an ignore rule as Risk accepted, the state it gives the finding', () => {
    const tags = card(true, true)
      .findAll('tbody tr')
      .map((row) => row.find('td').text())
    expect(tags).toEqual(['Not affected', 'Risk accepted', 'Risk accepted', 'Not affected'])
  })
})

/**
 * The Triage cell and its "Note and more…" panel (issue 1205, G2 with the quick buttons), with the
 * FR-7 gates: justification chips appear iff not_affected is the target; Save stays disabled
 * until the draft is legal; no can_triage → everything read-only; T<now → read-only with the
 * history note; risk-accept button exists only with can_accept_audit_final. The cell and the panel
 * share one draft, so both Save buttons send the same body.
 */
import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'

import TriagePanel from '@/components/triage/TriagePanel.vue'
import type { FindingRow } from '@/stores/findings'

const finding: FindingRow = {
  finding_key: 'k1',
  cve_id: 'CVE-2024-0001',
  scanner: 'trivy',
  severity: 'HIGH',
  severity_canonical: 'high',
  image_repo: 'nginx',
  tag: '1.25',
  package_name: 'openssl',
  installed_version: '3.0.1',
  fixed_version: null,
  fixable: false,
  epss: null,
  kev: false,
  ptype: null,
  state: 'open',
  overdue: false,
  due_at: null,
}

const wrappers: VueWrapper[] = []
afterEach(() => {
  for (const w of wrappers.splice(0)) w.unmount()
  document.body.innerHTML = ''
})

function panel(over: Record<string, unknown> = {}) {
  const w = mount(TriagePanel, {
    props: {
      finding,
      canTriage: true,
      canAcceptFinal: false,
      historical: false,
      saving: false,
      error: null,
      currentUser: 'admin',
      ...over,
    },
    attachTo: document.body,
  })
  wrappers.push(w)
  return w
}

type W = VueWrapper
const cell = (w: W) => w.find('aside.triage')
const pop = (w: W) => w.find('.pop')
const cellSave = (w: W) => cell(w).find('.ui-btn--primary')
const popSave = (w: W) => pop(w).find('.ui-btn--primary')
const moreBtn = (w: W) => cell(w).findAll('button').find((b) => b.text() === 'Note and more…')!
const stateBtn = (w: W, label: string) => w.findAll('.state-opt').find((b) => b.text() === label)!
const disabled = (b: { element: Element }) => (b.element as HTMLButtonElement).disabled
async function openMore(w: W) {
  await moreBtn(w).trigger('click')
  await nextTick()
}

describe('the Triage cell (issue 1205)', () => {
  it('holds Assigned to, the four state buttons, "Note and more…" and Save, and no legend', () => {
    const w = panel()
    expect(cell(w).text()).toContain('Assigned to')
    expect(cell(w).findAll('.state-opt').map((b) => b.text())).toEqual(['Open', 'Acknowledge', 'Not affected', 'Resolve'])
    expect(moreBtn(w).exists()).toBe(true)
    expect(cellSave(w).exists()).toBe(true)
    expect(pop(w).exists()).toBe(false)
    expect(w.find('.presence-note').exists()).toBe(false)
    expect(w.text()).not.toContain('drops off')
  })

  it('"Note and more…" opens the panel with a dark head, and a second click closes it', async () => {
    const w = panel()
    await openMore(w)
    expect(pop(w).exists()).toBe(true)
    expect(pop(w).find('.pop-head').classes()).toContain('pop-head--band')
    expect(pop(w).attributes('aria-label')).toBe('Triage: CVE-2024-0001')
    expect(moreBtn(w).attributes('aria-expanded')).toBe('true')
    await openMore(w)
    expect(pop(w).exists()).toBe(false)
  })

  it('the panel takes the focus, and Escape gives it back to "Note and more…" with the draft kept', async () => {
    const w = panel()
    await openMore(w)
    await nextTick()
    expect(document.activeElement).toBe(pop(w).element)
    await pop(w).find('#triage-notes').setValue('kept')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(pop(w).exists()).toBe(false)
    expect(document.activeElement).toBe(moreBtn(w).element)
    await openMore(w)
    expect((pop(w).find('#triage-notes').element as HTMLTextAreaElement).value).toBe('kept')
  })

  it('one draft: a state in the cell and a note in the panel, the same body from either Save', async () => {
    const w = panel()
    await stateBtn(w, 'Acknowledge').trigger('click')
    await openMore(w)
    await pop(w).find('#triage-notes').setValue('checked the image')
    await popSave(w).trigger('click')
    expect(pop(w).exists()).toBe(false) // a save closes the panel
    await cellSave(w).trigger('click')
    const body = { state: 'acknowledged', notes: 'checked the image' }
    expect(w.emitted('save')).toEqual([[body], [body]])
  })

  it('a note only: the draft saves without a state change', async () => {
    const w = panel()
    await openMore(w)
    await pop(w).find('#triage-notes').setValue('looked into it')
    await cellSave(w).trigger('click')
    expect(w.emitted('save')![0]![0]).toEqual({ notes: 'looked into it' })
  })

  it('the note uses the shared text box in the prose face (issue 1050)', async () => {
    const w = panel()
    await openMore(w)
    expect(pop(w).find('#triage-notes').classes()).toEqual(['set-input', 'set-input--prose'])
  })
})

describe('Not affected and its reason (operator, 2026-11-16, question 2 option A)', () => {
  it('a click on Not affected opens the panel at the reason; Save stays off until a reason', async () => {
    const w = panel()
    expect(w.find('.vex-chips').exists()).toBe(false)
    await stateBtn(w, 'Not affected').trigger('click')
    await nextTick()
    expect(pop(w).find('.vex-chips').exists()).toBe(true)
    expect(cell(w).find('.vex-chips').exists()).toBe(false)
    expect(pop(w).text()).toContain('Reason (required)')
    expect(pop(w).text()).toContain('Select a reason for Not affected.')
    expect(cell(w).text()).not.toContain('Select a reason')
    expect(pop(w).text()).not.toContain('CISA')
    expect(pop(w).find('.vex-chips').attributes('aria-label')).toBe('Reason for Not affected')
    expect(disabled(cellSave(w))).toBe(true)
    expect(disabled(popSave(w))).toBe(true)

    await pop(w).findAll('.vex-chip')[0]!.trigger('click')
    expect(disabled(cellSave(w))).toBe(false)
    await popSave(w).trigger('click')
    expect(w.emitted('save')![0]![0]).toEqual({ state: 'not_affected', vex_justification: 'component_not_present' })
  })

  it('switching away from not_affected clears the justification from the draft', async () => {
    const w = panel()
    await stateBtn(w, 'Not affected').trigger('click')
    await nextTick()
    await pop(w).findAll('.vex-chip')[0]!.trigger('click')
    await stateBtn(w, 'Acknowledge').trigger('click')
    expect(w.find('.vex-chips').exists()).toBe(false)
    await cellSave(w).trigger('click')
    expect(w.emitted('save')![0]![0]).toEqual({ state: 'acknowledged' })
  })
})

describe('the lines that explain the state are in the panel (operator, 2026-11-16, question 1 option B)', () => {
  it.each([
    ['risk_accepted', null],
    ['stale', 'risk_accepted'],
  ])('a triager on %s (kept: %s): the state is locked, the role line is in the panel, the note stays open', async (state, pre) => {
    const w = panel({ finding: { ...finding, state, pre_stale_status: pre } })
    for (const b of w.findAll('.state-opt')) expect(disabled(b)).toBe(true)
    expect(cell(w).find('.triage-accept-locked').exists()).toBe(false)
    await openMore(w)
    expect(pop(w).find('.triage-accept-locked').text()).toContain('can_accept_audit_final')
    expect(disabled(pop(w).find('#triage-notes'))).toBe(false)
  })

  it('a lead on a risk-accepted finding can change the state, and gets no lock line', async () => {
    const w = panel({ finding: { ...finding, state: 'risk_accepted' }, canAcceptFinal: true })
    for (const b of w.findAll('.state-opt')) expect(disabled(b)).toBe(false)
    await openMore(w)
    expect(w.find('.triage-accept-locked').exists()).toBe(false)
  })

  it.each(['risk_accepted', 'stale'])('the block of a %s finding is in the panel, not in the cell', async (state) => {
    const w = panel({ finding: { ...finding, state }, canAcceptFinal: true })
    expect(cell(w).find('.ro-state').exists()).toBe(false)
    await openMore(w)
    expect(pop(w).find('.ro-state').exists()).toBe(true)
  })

  it('no can_triage: the controls are off, "Note and more…" opens and its line names the permission', async () => {
    const w = panel({ canTriage: false })
    for (const b of w.findAll('.state-opt')) expect(disabled(b)).toBe(true)
    expect(disabled(cellSave(w))).toBe(true)
    expect(cell(w).text()).not.toContain('can_triage')
    expect(disabled(moreBtn(w))).toBe(false)
    await openMore(w)
    expect(pop(w).text()).toContain('can_triage')
    expect(disabled(popSave(w))).toBe(true)
  })

  it('T<now: read-only, and the history line is in the panel, even with can_triage', async () => {
    const w = panel({ historical: true })
    expect(disabled(cellSave(w))).toBe(true)
    expect(cell(w).text()).not.toContain('past time')
    await openMore(w)
    expect(pop(w).find('.triage-locked').text()).toBe(
      'This page shows the state at a past time. You cannot change it here. To change the state, select Back to now.',
    )
  })
})

describe('the risk acceptance button', () => {
  it('is in the panel, only with can_accept_audit_final', async () => {
    const w = panel()
    await openMore(w)
    expect(pop(w).find('.ui-btn--ghost').exists()).toBe(false)
    const lead = panel({ canAcceptFinal: true })
    expect(cell(lead).find('.ui-btn--ghost').exists()).toBe(false)
    await openMore(lead)
    expect(pop(lead).find('.ui-btn--ghost').text()).toBe('Accept the risk of this CVE…')
  })

  it('closes the panel and asks the page for the window', async () => {
    const w = panel({ canAcceptFinal: true })
    await openMore(w)
    await pop(w).find('.ui-btn--ghost').trigger('click')
    expect(w.emitted('riskAccept')).toHaveLength(1)
    expect(pop(w).exists()).toBe(false)
  })
})

describe('the lines that answer a save stay in the cell (operator, 2026-11-16, B2)', () => {
  it('the save error shows in the cell', () => {
    const w = panel({ error: 'Another person changed this finding.' })
    expect(cell(w).find('[role="alert"]').text()).toBe('Another person changed this finding.')
  })

  it('shows no Undo until the parent says there is a change to undo', () => {
    expect(panel().find('.triage-undo').exists()).toBe(false)
    expect(panel({ undo: null }).find('.triage-undo').exists()).toBe(false)
  })

  it('Undo is in the cell, names both states by their display names and emits undo', async () => {
    const w = panel({
      finding: { ...finding, state: 'not_affected' },
      undo: { from: 'open', to: 'not_affected' },
    })
    const line = cell(w).find('.triage-undo')
    expect(line.find('span').text()).toBe('You changed the state from Open to Not affected just now.')
    await line.find('button').trigger('click')
    expect(w.emitted('undo')).toHaveLength(1)
    expect(w.emitted('save')).toBeUndefined()
  })

  it('Undo drops the picked target, so the undone state does not read as a pending change', async () => {
    const w = panel({ undo: { from: 'open', to: 'acknowledged' } })
    const on = () => w.find('.state-opt-on').text()
    await stateBtn(w, 'Resolve').trigger('click')
    expect(on()).toBe('Resolve')
    await w.find('.triage-undo button').trigger('click')
    expect(on()).toBe('Open') // back to the finding's own state, nothing pending
  })

  it('Undo is not offered on a read-only cell, and waits while a save is running', () => {
    const offer = { from: 'open', to: 'acknowledged' }
    expect(panel({ undo: offer, canTriage: false }).find('.triage-undo').exists()).toBe(false)
    expect(panel({ undo: offer, historical: true }).find('.triage-undo').exists()).toBe(false)
    expect(panel({ undo: offer, saving: true }).find('.triage-undo button').attributes('disabled')).toBeDefined()
  })
})

describe('the text of the cell and the panel (strict STE, comments 6880398386 and 6909666536)', () => {
  it('both Save buttons say Save, and the line under Save names Activity', async () => {
    const w = panel()
    expect(cellSave(w).text()).toBe('Save')
    await openMore(w)
    expect(popSave(w).text()).toBe('Save')
    expect(pop(w).find('#triage-notes').attributes('placeholder')).toBe('Add a note for Activity…')
    expect(pop(w).find('.triage-foot').text()).toBe('JAVV records who saved each change and when. Activity lists the changes.')
  })

  it('the block of a Risk accepted finding', async () => {
    const w = panel({ finding: { ...finding, state: 'risk_accepted' }, canAcceptFinal: true })
    await openMore(w)
    const block = pop(w).find('.ro-risk')
    expect(block.find('b').text()).toBe('Set by a decision')
    expect(block.find('span').text()).toBe(
      'A decision on this CVE sets this state. The decision has a scope, an approver and an expiry date. ' +
        'To change this state, use Decisions on this CVE.',
    )
  })

  it('the block of a Stale finding', async () => {
    const w = panel({ finding: { ...finding, state: 'stale' }, canAcceptFinal: true })
    await openMore(w)
    const block = pop(w).find('.ro-stale')
    expect(block.find('b').text()).toBe('Set by JAVV')
    expect(block.find('span').text()).toBe(
      'No recent scan confirms this finding. The data can be old. If you set a state, it replaces Stale.',
    )
  })

  it('the line of a role that cannot change a risk acceptance', async () => {
    const w = panel({ finding: { ...finding, state: 'risk_accepted' } })
    await openMore(w)
    expect(pop(w).find('.triage-accept-locked').text()).toBe(
      'To change a risk acceptance, your role must allow risk acceptance (can_accept_audit_final). ' +
        'You can still assign this finding and add a note.',
    )
  })

  it('the line of a role that cannot triage', async () => {
    const w = panel({ canTriage: false })
    await openMore(w)
    expect(pop(w).find('.triage-locked').text()).toBe(
      'Your role does not allow triage (can_triage). To change the state, ask a triager, a security lead or an admin.',
    )
  })
})

describe('the draft after a save (review round 1)', () => {
  async function saveNote(w: W) {
    await stateBtn(w, 'Acknowledge').trigger('click')
    await openMore(w)
    await pop(w).find('#triage-notes').setValue('checked the image')
    await popSave(w).trigger('click')
    await w.setProps({ saving: true })
  }

  it('a save that went through empties the draft, so the note is not sent again', async () => {
    const w = panel()
    await saveNote(w)
    await w.setProps({ saving: false, error: null })
    expect(disabled(cellSave(w))).toBe(true)
    await openMore(w)
    expect((pop(w).find('#triage-notes').element as HTMLTextAreaElement).value).toBe('')
  })

  it('a save that failed keeps the draft, so the user can save it again', async () => {
    const w = panel()
    await saveNote(w)
    await w.setProps({ saving: false, error: 'Another person changed this finding.' })
    expect(disabled(cellSave(w))).toBe(false)
    await openMore(w)
    expect((pop(w).find('#triage-notes').element as HTMLTextAreaElement).value).toBe('checked the image')
  })

  it('a change made while the save runs stays in the draft (review round 2)', async () => {
    const w = panel()
    await saveNote(w)
    await stateBtn(w, 'Resolve').trigger('click')
    await w.setProps({ saving: false, error: null })
    expect(w.find('.state-opt-on').text()).toBe('Resolve')
    expect(disabled(cellSave(w))).toBe(false)
  })

  it('Undo leaves a typed note in the draft', async () => {
    const w = panel({ undo: { from: 'open', to: 'acknowledged' } })
    await openMore(w)
    await pop(w).find('#triage-notes').setValue('not yet saved')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    await w.find('.triage-undo button').trigger('click')
    await w.setProps({ saving: true })
    await w.setProps({ saving: false, undo: null })
    await openMore(w)
    expect((pop(w).find('#triage-notes').element as HTMLTextAreaElement).value).toBe('not yet saved')
  })
})

describe('the guards of Save and of the panel (review round 1)', () => {
  it('while a save runs, both Save buttons are off, with a legal draft', async () => {
    const w = panel()
    await stateBtn(w, 'Acknowledge').trigger('click')
    await openMore(w)
    await w.setProps({ saving: true })
    expect(disabled(cellSave(w))).toBe(true)
    expect(disabled(popSave(w))).toBe(true)
  })

  it('history turns Save off, also with a legal draft', async () => {
    const w = panel()
    await stateBtn(w, 'Acknowledge').trigger('click')
    expect(disabled(cellSave(w))).toBe(false)
    await w.setProps({ historical: true })
    expect(disabled(cellSave(w))).toBe(true)
  })

  it('history turns the note and the risk button in the panel off', async () => {
    const w = panel({ historical: true, canAcceptFinal: true })
    await openMore(w)
    expect(disabled(pop(w).find('#triage-notes'))).toBe(true)
    const risk = pop(w).findAll('button').find((b) => b.text() === 'Accept the risk of this CVE…')!
    expect(disabled(risk)).toBe(true)
  })
})

describe('another finding', () => {
  it('drops the draft and closes the panel', async () => {
    const w = panel()
    await stateBtn(w, 'Acknowledge').trigger('click')
    await openMore(w)
    await pop(w).find('#triage-notes').setValue('for k1')
    await w.setProps({ finding: { ...finding, finding_key: 'k2' } })
    expect(pop(w).exists()).toBe(false)
    expect(disabled(cellSave(w))).toBe(true)
  })
})

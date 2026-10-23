/**
 * The edit dialog of the Approvals queue and the expiry (issue 984). An edit is revoke + new,
 * and the new decision keeps the current expiry unless the edit sets one. So a decision whose
 * expiry has passed needs a new date, and a new date starts at tomorrow in UTC.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { EXPIRY_PASSED_TYPE } from '@/api/problem'
import { EXPIRY_REFUSED, type ApprovalRow } from '@/approvals/viewModel'
import EditDecisionDialog from '@/components/approvals/EditDecisionDialog.vue'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    editApiV1DecisionsDecisionIdPatch: vi.fn<() => Promise<unknown>>(),
  }),
)
vi.mock('@/api/client', () => ({ client: {} }))

import { editApiV1DecisionsDecisionIdPatch } from '@/api/generated'

const decision = (expiry: string | null): ApprovalRow => ({
  decision_id: 'd-1',
  cve_id: 'CVE-2026-0001',
  type: 'risk_accepted',
  scope: { namespaces: [], images: [] },
  apply_both_scanners: true,
  scanner: null,
  justification: 'No fix yet.',
  vex_justification: null,
  expiry,
  created_by: 'lead',
  created_at: '2026-10-01T00:00:00+00:00',
})

const saveButton = () =>
  [...document.body.querySelectorAll('button')].find((b) => b.textContent!.includes('Revoke + re-issue'))!

async function open(expiry: string | null, edit: { expiry?: string; justification?: string } = {}) {
  const w = mount(EditDecisionDialog, { props: { decision: decision(expiry) }, attachTo: document.body })
  if (edit.justification !== undefined) {
    const just = document.body.querySelector<HTMLTextAreaElement>('#ed-just')!
    just.value = edit.justification
    just.dispatchEvent(new Event('input'))
  }
  if (edit.expiry !== undefined) {
    const date = document.body.querySelector<HTMLInputElement>('#ed-expiry')!
    date.value = edit.expiry
    date.dispatchEvent(new Event('input'))
  }
  await w.vm.$nextTick()
  return w
}

describe('EditDecisionDialog expiry (issue 984)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-23T12:00:00Z'))
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })
  afterEach(() => vi.useRealTimers())

  it('the date field starts at tomorrow in UTC', async () => {
    await open('2026-12-31')
    expect(document.body.querySelector('#ed-expiry')!.getAttribute('min')).toBe('2026-10-24')
  })

  it('a decision that has expired cannot keep its date, and says why', async () => {
    await open('2026-09-30', { justification: 'Still no fix.' })
    expect(saveButton().disabled).toBe(true)
    expect(document.body.textContent).toContain(EXPIRY_REFUSED)
  })

  it('a new date after today renews an expired decision', async () => {
    vi.mocked(editApiV1DecisionsDecisionIdPatch).mockResolvedValueOnce({
      data: {},
      request: {},
      response: { ok: true, status: 200 },
    } as never)
    await open('2026-09-30', { expiry: '2026-11-30' })
    expect(saveButton().disabled).toBe(false)
    saveButton().click()
    await flushPromises()
    expect(vi.mocked(editApiV1DecisionsDecisionIdPatch).mock.calls[0]![0]).toMatchObject({
      body: { expiry: '2026-11-30' },
    })
  })

  it('a decision that has not expired keeps its date on a change of reason', async () => {
    await open('2026-12-31', { justification: 'Vendor says Q1.' })
    expect(saveButton().disabled).toBe(false)
    expect(document.body.textContent).not.toContain(EXPIRY_REFUSED)
  })

  it('a typed date of today or before cannot be sent', async () => {
    for (const day of ['2026-10-23', '2026-01-01']) {
      document.body.innerHTML = ''
      await open('2026-12-31', { expiry: day })
      expect(saveButton().disabled, day).toBe(true)
    }
  })

  it('a decision with no expiry can still change its reason', async () => {
    await open(null, { justification: 'Accepted for good.' })
    expect(saveButton().disabled).toBe(false)
  })

  it('the server refusing the expiry names the date', async () => {
    vi.mocked(editApiV1DecisionsDecisionIdPatch).mockResolvedValueOnce({
      error: { title: 'refused', status: 422, type: EXPIRY_PASSED_TYPE },
      request: {},
      response: { ok: false, status: 422 },
    } as never)
    await open('2026-12-31', { justification: 'Changed.' })
    saveButton().click()
    await flushPromises()
    expect(document.body.querySelector('.modal-error')?.textContent).toBe(EXPIRY_REFUSED)
  })
})

/**
 * The bulk triage dialog when the current filters can't drive a bulk action (issue 674): it
 * says what to do and offers one way out, never a dead "Apply" beside a refusal.
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { bulkTriageApiV1FindingsBulkTriagePost } from '@/api/generated'
import BulkTriageBar from '@/components/triage/BulkTriageBar.vue'
import { useClusterStore } from '@/stores/cluster'
import { FINDINGS_FIELDS } from '@/filters/fields.config'

vi.mock('@/api/generated', async (importOriginal) =>
  (await import('./helpers/mockSdk')).mockSdk(importOriginal, {
    bulkTriageApiV1FindingsBulkTriagePost: vi.fn<() => Promise<unknown>>(),
    listClustersApiV1ClustersGet: vi.fn<() => Promise<unknown>>(),
  }),
)

const open = async (selections: Record<string, string[]>, total: number | null = 12) => {
  const w = mount(BulkTriageBar, {
    props: { fields: FINDINGS_FIELDS, selections, total, canTriage: true, canAcceptFinal: true, historical: false },
    attachTo: document.body,
  })
  await w.findAll('button').find((b) => b.text().includes('Bulk triage'))!.trigger('click')
  return w
}
const buttons = () => [...document.body.querySelectorAll('button')].map((b) => b.textContent!.trim())

describe('BulkTriageBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    document.body.innerHTML = ''
  })

  it('with no filter: says to add one, and offers Close alone', async () => {
    await open({})
    expect(document.body.textContent).toContain('Add a filter first.')
    expect(buttons()).toContain('Close')
    expect(buttons()).not.toContain('Cancel')
    expect(buttons().some((t) => t.startsWith('Apply'))).toBe(false)
  })

  it('with a filter it cannot follow: names the filter to remove, and offers Close alone', async () => {
    await open({ severity: ['critical'], namespace: ['payments'] })
    expect(document.body.textContent).toContain('Remove this filter first: Namespace.')
    expect(buttons().some((t) => t.startsWith('Apply'))).toBe(false)
  })

  // issue 909: the reasons of Not affected carry a plain label, not an internal name
  it('Not affected: the reasons carry the label Reason (required)', async () => {
    await open({ severity: ['critical'] })
    const notAffected = [...document.body.querySelectorAll<HTMLButtonElement>('.state-opt')].find(
      (b) => b.textContent!.trim() === 'Not affected',
    )!
    notAffected.click()
    await new Promise((r) => setTimeout(r))
    expect(document.body.querySelector('.vex-chips')).not.toBeNull()
    expect(document.body.textContent).toContain('Reason (required)')
    expect(document.body.textContent).not.toContain('CISA')
  })

  it('with a usable filter: the form, with Cancel and Apply', async () => {
    await open({ severity: ['critical'] })
    expect(document.body.textContent).not.toContain('Add a filter first.')
    expect(buttons()).toContain('Cancel')
    expect(buttons().some((t) => t.startsWith('Apply'))).toBe(true)
  })

  // issue 833, F1: the count came from the last answer, so a refused read showed the old count
  it.each([
    [12, '≈ 12 findings', false],
    [null, 'count unknown', true],
  ] as const)('with a total of %s: says "%s", Apply disabled is %s', async (total, label, off) => {
    const w = await open({ severity: ['critical'] }, total)
    const assignee = document.body.querySelector<HTMLInputElement>('#bulk-assignee')!
    assignee.value = 'bob'
    assignee.dispatchEvent(new Event('input'))
    await w.vm.$nextTick()
    expect(document.body.querySelector('.lens-count')!.textContent!.trim()).toBe(label)
    const apply = [...document.body.querySelectorAll('button')].find((b) =>
      b.textContent!.includes('Apply to matching findings'),
    )!
    expect(apply.disabled).toBe(off)
  })

  // issue 892 ruling 6: the server refuses a state change over risk-accepted findings with the
  // count; the bar says that, not "check the backend connection"
  it('a refusal shows the reason the server gives', async () => {
    useClusterStore().selectedId = 'c-1'
    const reason =
      '2 of the 3 selected findings are risk-accepted. Changing their state requires can_accept_audit_final.'
    vi.mocked(bulkTriageApiV1FindingsBulkTriagePost).mockResolvedValueOnce({
      error: { title: reason, status: 403 },
      request: {},
      response: { ok: false, status: 403 },
    } as never)
    const w = await open({ severity: ['critical'] })
    const open_ = [...document.body.querySelectorAll<HTMLButtonElement>('.state-opt')].find(
      (b) => b.textContent!.trim() === 'Open',
    )!
    open_.click()
    await w.vm.$nextTick()
    ;[...document.body.querySelectorAll('button')].find((b) => b.textContent!.includes('Apply to matching'))!.click()
    await vi.waitFor(() => expect(document.body.querySelector('.bulk-error')?.textContent).toBe(reason))
  })
})

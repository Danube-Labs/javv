/**
 * The window that deletes a saved view (issue 1140, R3): the request goes only from its button,
 * a 404 counts as deleted, and each refused status has its own text.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/api/generated', () => ({ deleteViewApiV1ViewsViewIdDelete: vi.fn<(...args: unknown[]) => Promise<unknown>>() }))
vi.mock('@/api/client', () => ({ client: {} }))

import { STORE_READ_ONLY_TYPE } from '@/api/problem'
import { deleteViewApiV1ViewsViewIdDelete } from '@/api/generated'
import DeleteViewDialog from '@/components/saved/DeleteViewDialog.vue'
import { viewDeleteFailureCopy } from '@/findings/savedViews'

const del = vi.mocked(deleteViewApiV1ViewsViewIdDelete)
async function confirmWith(answer: unknown) {
  del.mockReset()
  del.mockResolvedValue(answer as never)
  const w = mount(DeleteViewDialog, { props: { viewId: 'v1', name: 'Prod backlog' }, attachTo: document.body })
  expect(del).not.toHaveBeenCalled()
  await w.findAll('button').find((b) => b.text() === 'Delete view')!.trigger('click')
  await flushPromises()
  return w
}

describe('DeleteViewDialog', () => {
  it('asks with the name, says it cannot be undone, and has Cancel and Delete view', () => {
    const w = mount(DeleteViewDialog, { props: { viewId: 'v1', name: 'Prod backlog' }, attachTo: document.body })
    expect(w.get('.modal-head h3').text()).toBe('Delete Prod backlog?')
    expect(w.get('.modal-head').text()).toContain('You cannot undo this.')
    expect(w.findAll('.modal-actions button').map((b) => b.text())).toEqual(['Cancel', 'Delete view'])
    w.unmount()
  })

  it.each([204, 404])('a %i counts as deleted', async (status) => {
    const w = await confirmWith({ response: { ok: status === 204, status } })
    expect(del).toHaveBeenCalledWith({ path: { view_id: 'v1' } })
    expect(w.emitted('deleted')).toHaveLength(1)
    w.unmount()
  })

  it.each([403, 409, 429, 500])('a %i stays in the window and says why', async (status) => {
    const w = await confirmWith({ response: { ok: false, status } })
    expect(w.emitted('deleted')).toBeUndefined()
    expect(w.get('[role="alert"]').text()).toBe(viewDeleteFailureCopy(status, false))
    w.unmount()
  })

  it('a full disk says so', async () => {
    const w = await confirmWith({ response: { ok: false, status: 503 }, error: { type: STORE_READ_ONLY_TYPE } })
    expect(w.get('[role="alert"]').text()).toMatch(/read-only/)
    w.unmount()
  })
})

describe('viewDeleteFailureCopy', () => {
  it('has its own text for each refused status, and a lost answer does not say that nothing happened', () => {
    const texts = [403, 409, 429, 500].map((s) => viewDeleteFailureCopy(s, false))
    expect(new Set([...texts, viewDeleteFailureCopy(0, true)]).size).toBe(5)
    expect(viewDeleteFailureCopy(0, false)).toMatch(/possibly deleted/)
    expect(viewDeleteFailureCopy(504, false)).toBe(viewDeleteFailureCopy(0, false))
  })
})

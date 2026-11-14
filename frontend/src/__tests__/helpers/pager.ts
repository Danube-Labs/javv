/** What a user does with the shared GridPager under a table, and what it then says. */
import { flushPromises, type VueWrapper } from '@vue/test-utils'

type Wrapper = Pick<VueWrapper, 'get' | 'findAll'>

export const pagerText = (w: Wrapper) => w.get('.pager-info').text()

export async function nextPage(w: Wrapper) {
  await w.get('.pager').findAll('button').find((b) => b.text() === 'Next')!.trigger('click')
  await flushPromises()
}

export async function pickRowsPerPage(w: Wrapper, size: number) {
  await w.get('.pager select').setValue(String(size))
  await flushPromises()
}

export const bodyRows = (w: Wrapper) => w.findAll('tbody tr').length

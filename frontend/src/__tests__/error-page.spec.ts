/** The shared layout for a page that cannot be shown (issue 675): one h1, the code hidden from
 * assistive tech (the title already says it), the detail chip only when there is a detail. */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ErrorPage from '@/components/system/ErrorPage.vue'

const base = { code: 'Error', title: 'JAVV cannot show this page', hint: 'Something went wrong.' }

describe('ErrorPage', () => {
  it('shows the code, the title as the only h1, and the message', () => {
    const w = mount(ErrorPage, { props: base })
    expect(w.findAll('h1')).toHaveLength(1)
    expect(w.get('h1').text()).toBe('JAVV cannot show this page')
    expect(w.get('.ep-code').text()).toBe('Error')
    expect(w.get('.ep-code').attributes('aria-hidden')).toBe('true')
    expect(w.get('.ep-hint').text()).toBe('Something went wrong.')
  })

  it('has no detail chip without a detail', () => {
    expect(mount(ErrorPage, { props: base }).find('.ep-detail').exists()).toBe(false)
  })

  it('shows the detail when given one', () => {
    const w = mount(ErrorPage, { props: { ...base, detail: '/reports/old-link' } })
    expect(w.get('.ep-detail').text()).toBe('/reports/old-link')
  })

  it('renders the ways out it is given', () => {
    const w = mount(ErrorPage, { props: base, slots: { default: '<button>Try again</button>' } })
    expect(w.get('.ep-actions button').text()).toBe('Try again')
  })
})

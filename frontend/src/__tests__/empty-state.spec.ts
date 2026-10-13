/**
 * The cold-start state is the whole page before the first cluster (issue 829), so its title is
 * the page's h1; everywhere else the empty state sits under a page title and stays an h2.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EmptyState from '@/components/ui/EmptyState.vue'

describe('EmptyState title level', () => {
  it('is an h2 under a page title', () => {
    const w = mount(EmptyState, { props: { title: 'No saved views yet' } })
    expect(w.find('h2').text()).toBe('No saved views yet')
    expect(w.find('h1').exists()).toBe(false)
  })

  it('is the h1 when the state is the page', () => {
    const w = mount(EmptyState, { props: { title: 'No clusters registered yet', pageTitle: true } })
    expect(w.find('h1').text()).toBe('No clusters registered yet')
    expect(w.find('h2').exists()).toBe(false)
  })
})

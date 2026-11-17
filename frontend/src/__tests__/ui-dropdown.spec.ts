/**
 * The kit dropdown: its open and close motion. Every menu has `t-pop`. A menu with the dark head
 * of a window can ask for the genie motion of the popovers, `t-pour` (issue 1240, decision 5).
 */
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { h } from 'vue'

import UiDropdown from '@/components/ui/UiDropdown.vue'

let unmount: (() => void) | null = null
afterEach(() => {
  unmount?.()
  unmount = null
})

function menu(motion?: 't-pop' | 't-pour') {
  const w = mount(UiDropdown, {
    props: { open: true, ...(motion ? { motion } : {}) },
    slots: { default: () => h('div', { class: 'menu' }, 'items') },
    attachTo: document.body,
    // the real Transition, so its classes show
    global: { stubs: { transition: false } },
  })
  unmount = () => w.unmount()
  return w
}

describe('the motion of the kit dropdown', () => {
  it('a menu opens with t-pop when it asks for nothing', async () => {
    const w = menu()
    await w.setProps({ open: false })
    await w.setProps({ open: true })
    expect(w.find('.menu').classes()).toContain('t-pop-enter-active')
  })

  it('a menu that asks for t-pour opens with it', async () => {
    const w = menu('t-pour')
    await w.setProps({ open: false })
    await w.setProps({ open: true })
    expect(w.find('.menu').classes()).toContain('t-pour-enter-active')
    expect(w.find('.menu').classes()).not.toContain('t-pop-enter-active')
  })
})

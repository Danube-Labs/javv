/**
 * UiSearchBox (issue 1055): the kit piece for a search box. It is the base.css row (`.search-box`,
 * issue 1053) with the magnifier, or the same box as the search card over a filter list
 * (`.facet-search`). The class of a screen goes on the row and the other attributes go on the input.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import UiSearchBox from '@/components/ui/UiSearchBox.vue'

describe('UiSearchBox', () => {
  it('is the shared search row with the magnifier and one bare input', () => {
    const w = mount(UiSearchBox)
    expect(w.classes()).toEqual(['search-box'])
    expect(w.findAll('input')).toHaveLength(1)
    expect(w.find('input').classes()).toEqual([])
    const icon = w.findComponent(AppIcon)
    expect(icon.props()).toMatchObject({ name: 'search', size: 13 })
  })

  it('card is the search card over a filter list, with the larger magnifier', () => {
    const w = mount(UiSearchBox, { props: { card: true } })
    expect(w.classes()).toEqual(['facet-search'])
    expect(w.findComponent(AppIcon).props('size')).toBe(14)
  })

  it('puts the class of the screen on the row, and the other attributes on the input', async () => {
    let entered = ''
    const w = mount(UiSearchBox, {
      attrs: {
        class: 'filter-vsearch',
        placeholder: 'Filter values…',
        'aria-label': 'Search findings',
        onKeydown: (e: KeyboardEvent) => (entered = e.key),
      },
    })
    expect(w.classes()).toEqual(['search-box', 'filter-vsearch'])
    const input = w.find('input')
    expect(input.attributes()).toMatchObject({ placeholder: 'Filter values…', 'aria-label': 'Search findings' })
    expect(input.attributes('class')).toBeUndefined()
    expect(w.attributes('placeholder')).toBeUndefined()
    await input.trigger('keydown', { key: 'Enter' })
    expect(entered).toBe('Enter')
  })

  it('follows a change of the attributes and the class of the screen', async () => {
    // Add filter changes the placeholder when the user picks another field
    const Host = defineComponent({
      components: { UiSearchBox },
      setup: () => ({ field: ref('Namespace'), wide: ref(false) }),
      template: '<UiSearchBox :class="{ wide }" :placeholder="`${field}…`" />',
    })
    const w = mount(Host)
    w.vm.field = 'Image'
    w.vm.wide = true
    await nextTick()
    expect(w.find('input').attributes('placeholder')).toBe('Image…')
    expect(w.classes()).toContain('wide')
  })

  it('works with v-model', async () => {
    const Host = defineComponent({
      components: { UiSearchBox },
      setup: () => ({ q: ref('old') }),
      template: '<UiSearchBox v-model="q" />',
    })
    const w = mount(Host)
    expect((w.find('input').element as HTMLInputElement).value).toBe('old')
    await w.find('input').setValue('new')
    expect(w.vm.q).toBe('new')
  })

  it('can take the value only: the box keeps what the user types, and shows a new value from the screen', async () => {
    // the filter searches apply on Enter and read the box, so they give the value and take no changes back
    const Host = defineComponent({
      components: { UiSearchBox },
      setup: () => ({ q: ref('') }),
      template: '<UiSearchBox :model-value="q" />',
    })
    const w = mount(Host)
    const input = w.find('input').element as HTMLInputElement
    await w.find('input').setValue('typed')
    await nextTick()
    expect(input.value).toBe('typed')
    w.vm.q = 'applied'
    await nextTick()
    expect(input.value).toBe('applied')
  })
})

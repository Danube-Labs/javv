/**
 * UiSelect (issue 1055): the kit piece for a dropdown. It is a single select that wears the
 * base.css dropdown (`.set-select`, issue 1050); the screen writes the options in the slot.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import UiSelect from '@/components/ui/UiSelect.vue'

const OPTIONS = '<option value="viewer">viewer</option><option value="admin">admin</option>'

describe('UiSelect', () => {
  it('is one select that wears the shared dropdown, with the options of the screen', () => {
    const w = mount(UiSelect, { props: { modelValue: 'admin' }, slots: { default: OPTIONS } })
    expect(w.element.tagName).toBe('SELECT')
    expect(w.classes()).toEqual(['set-select'])
    expect(w.findAll('option').map((o) => o.attributes('value'))).toEqual(['viewer', 'admin'])
    expect((w.element as HTMLSelectElement).value).toBe('admin')
  })

  it('row takes the size of a table row', () => {
    const w = mount(UiSelect, { props: { modelValue: 'admin', row: true }, slots: { default: OPTIONS } })
    expect(w.classes()).toEqual(['set-select', 'set-select--row'])
  })

  it('small takes the small mono size of the pager', () => {
    const w = mount(UiSelect, { props: { modelValue: 'admin', small: true }, slots: { default: OPTIONS } })
    expect(w.classes()).toEqual(['set-select', 'set-select--small'])
  })

  it('passes the attributes of the screen to the select', () => {
    const w = mount(UiSelect, {
      props: { modelValue: 'admin' },
      slots: { default: OPTIONS },
      attrs: { id: 'inv-role', disabled: true, 'aria-label': 'Role for ana' },
    })
    expect(w.attributes()).toMatchObject({ id: 'inv-role', 'aria-label': 'Role for ana' })
    expect(w.attributes('disabled')).toBeDefined()
  })

  it('reports the pick', async () => {
    const w = mount(UiSelect, { props: { modelValue: 'admin' }, slots: { default: OPTIONS } })
    await w.setValue('viewer')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['viewer'])
  })
})

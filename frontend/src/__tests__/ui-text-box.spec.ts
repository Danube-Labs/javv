/**
 * UiTextBox and UiTextArea (issue 1055): the kit pieces for a field that people type in. Each one
 * is a single element that wears the base.css box (`.set-input`, issue 1050), so the attributes a
 * screen sets reach the element and the look stays in one place.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, ref } from 'vue'

import UiTextArea from '@/components/ui/UiTextArea.vue'
import UiTextBox from '@/components/ui/UiTextBox.vue'

describe('UiTextBox', () => {
  it('is one input that wears the shared box and nothing else', () => {
    const w = mount(UiTextBox, { props: { modelValue: 'x' } })
    expect(w.element.tagName).toBe('INPUT')
    expect(w.classes()).toEqual(['set-input'])
    expect(w.attributes('type')).toBe('text')
    expect(w.attributes('aria-invalid')).toBeUndefined()
  })

  it('num, prose and invalid add their looks, and invalid tells a screen reader', () => {
    const w = mount(UiTextBox, { props: { modelValue: '', num: true, prose: true, invalid: true } })
    expect(w.classes()).toEqual(
      expect.arrayContaining(['set-input', 'set-input--num', 'set-input--prose', 'set-input--invalid']),
    )
    expect(w.attributes('aria-invalid')).toBe('true')
  })

  it('takes the password, date and number types', () => {
    for (const type of ['password', 'date', 'number'] as const)
      expect(mount(UiTextBox, { props: { modelValue: '', type } }).attributes('type')).toBe(type)
  })

  it('passes the attributes of the screen to the input', () => {
    const w = mount(UiTextBox, {
      props: { modelValue: '', type: 'date' },
      attrs: { id: 'ed-expiry', min: '2026-11-01', placeholder: 'p', disabled: true, 'aria-label': 'Expiry' },
    })
    expect(w.attributes()).toMatchObject({ id: 'ed-expiry', min: '2026-11-01', placeholder: 'p', 'aria-label': 'Expiry' })
    expect(w.attributes('disabled')).toBeDefined()
  })

  it('reports what the user types, and shows the value the screen gives', async () => {
    const w = mount(UiTextBox, { props: { modelValue: 'old' } })
    expect((w.element as HTMLInputElement).value).toBe('old')
    await w.setValue('new')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['new'])
  })

  it('gives a number to v-model.number, for the number box of the time picker', async () => {
    const Host = defineComponent({
      components: { UiTextBox },
      setup: () => ({ n: ref<number | string>(7) }),
      template: '<UiTextBox v-model.number="n" type="number" />',
    })
    const w = mount(Host)
    await w.find('input').setValue('12')
    expect(w.vm.n).toBe(12)
  })
})

describe('UiTextArea', () => {
  it('is one text area that wears the shared box', () => {
    const w = mount(UiTextArea, { props: { modelValue: 'x' }, attrs: { rows: '3', id: 'ra-just' } })
    expect(w.element.tagName).toBe('TEXTAREA')
    expect(w.classes()).toEqual(['set-input'])
    expect(w.attributes()).toMatchObject({ rows: '3', id: 'ra-just' })
  })

  it('prose and invalid add their looks, and invalid tells a screen reader', () => {
    const w = mount(UiTextArea, { props: { modelValue: '', prose: true, invalid: true } })
    expect(w.classes()).toEqual(expect.arrayContaining(['set-input', 'set-input--prose', 'set-input--invalid']))
    expect(w.attributes('aria-invalid')).toBe('true')
  })

  it('reports what the user types', async () => {
    const w = mount(UiTextArea, { props: { modelValue: '' } })
    await w.setValue('why')
    expect(w.emitted('update:modelValue')?.at(-1)).toEqual(['why'])
  })
})

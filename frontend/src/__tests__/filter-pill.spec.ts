/**
 * The filter pill is a frame of separate buttons: the field button (it opens the field), the op
 * toggle on a negatable field, and the ✕. A button inside a button is not valid HTML, and the
 * keyboard could not reach the ✕ (issue 1140, step 5.4). The pill looks as before.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FilterPill from '@/components/filters/FilterPill.vue'
import { FINDINGS_FIELDS, isNegatable } from '@/filters/fields.config'

const field = (key: string) => FINDINGS_FIELDS.find((f) => f.key === key)!

describe('FilterPill', () => {
  it('has no button inside a button, and every button is reachable by the keyboard', () => {
    const w = mount(FilterPill, { props: { field: field('severity'), values: ['critical'], mode: 'is' } })
    expect(w.element.tagName).toBe('DIV')
    expect(w.findAll('button button')).toHaveLength(0)
    expect(w.findAll('[role="button"]')).toHaveLength(0)
    const buttons = w.findAll('button')
    expect(buttons.every((b) => b.attributes('tabindex') !== '-1')).toBe(true)
    expect(buttons.at(-1)!.attributes('aria-label')).toBe('Clear Severity')
  })

  it('opens from the field button, which names the whole filter', async () => {
    const w = mount(FilterPill, { props: { field: field('severity'), values: ['critical', 'high'], mode: 'is' } })
    const open = w.get('.fpill-open')
    expect(open.attributes('aria-label')).toBe('Edit the filter Severity: is one of critical, high')
    await open.trigger('click')
    expect(w.emitted('open')).toHaveLength(1)
  })

  it('clears from the ✕ and switches the mode from the op words, without opening the field', async () => {
    const neg = FINDINGS_FIELDS.find((f) => isNegatable(f))!
    const w = mount(FilterPill, { props: { field: neg, values: ['x'], mode: 'is' } })
    await w.get('.fpill-x').trigger('click')
    expect(w.emitted('clear')).toHaveLength(1)
    await w.get('button.fpill-op-btn').trigger('click')
    expect(w.emitted('toggleMode')).toHaveLength(1)
    expect(w.emitted('open')).toBeUndefined()
  })
})

/**
 * The filter pill is a frame of separate buttons: the field button (it opens the field), the op
 * toggle on a negatable field, and the ✕. A button inside a button is not valid HTML, and the
 * keyboard could not reach the ✕ (issue 1140, step 5.4). The pill looks as before.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import FilterBar from '@/components/filters/FilterBar.vue'
import FilterPill from '@/components/filters/FilterPill.vue'
import { FINDINGS_FIELDS, isNegatable, pillNote } from '@/filters/fields.config'
import { IMAGES_FIELDS } from '@/images/fields.config'

const field = (key: string) => FINDINGS_FIELDS.find((f) => f.key === key)!

describe('FilterPill', () => {
  it('has no button inside a button, and every button is reachable by the keyboard', () => {
    const w = mount(FilterPill, { props: { field: field('severity'), values: ['critical'], mode: 'is' } })
    expect(w.element.tagName).toBe('DIV')
    expect(w.findAll('button button')).toHaveLength(0)
    expect(w.findAll('[role="button"]')).toHaveLength(0)
    const buttons = w.findAll('button')
    expect(buttons.every((b) => b.attributes('tabindex') !== '-1')).toBe(true)
    expect(buttons.at(-1)!.attributes('aria-label')).toBe('Clear severity')
  })

  it('opens from the field button, which names the whole filter', async () => {
    const w = mount(FilterPill, { props: { field: field('severity'), values: ['critical', 'high'], mode: 'is' } })
    const open = w.get('.fpill-open')
    expect(open.attributes('aria-label')).toBe('Edit the filter severity: is one of critical, high')
    await open.trigger('click')
    expect(w.emitted('open')).toHaveLength(1)
  })

  // issue 1294: the Image filter matches every tag of the image until Tag or No tag narrows it
  it('the Image pill says all tags while Tag and No tag are off', () => {
    const image = field('image')
    const note = (selections: Record<string, string[]>) => pillNote(image, selections)
    expect(note({ image: ['shop/app'] })).toBe('all tags')
    expect(note({ image: ['shop/app'], attr: ['kev'] })).toBe('all tags')
    expect(note({ image: ['shop/app'], tag: ['1.4.1'] })).toBeNull()
    expect(note({ image: ['shop/app'], attr: ['untagged'] })).toBeNull()
    expect(note({ image: [] })).toBeNull()
    expect(pillNote(field('severity'), { severity: ['critical'] })).toBeNull()

    const w = mount(FilterPill, { props: { field: image, values: ['shop/app'], mode: 'is', note: 'all tags' } })
    expect(w.get('.fpill-note').text()).toBe('· all tags')
    expect(w.get('.fpill-open').attributes('aria-label')).toBe('Edit the filter image: is shop/app, all tags')
    const plain = mount(FilterPill, { props: { field: image, values: ['shop/app'], mode: 'is' } })
    expect(plain.find('.fpill-note').exists()).toBe(false)
  })

  it('the filter bar gives the Image pill its note, and takes it away for a Tag', async () => {
    const bar = (selections: Record<string, string[]>) =>
      mount(FilterBar, { props: { fields: FINDINGS_FIELDS, selections } })
    expect(bar({ image: ['shop/app'] }).get('.fpill-note').text()).toBe('· all tags')
    expect(bar({ image: ['shop/app'], tag: ['1.4.1'] }).find('.fpill-note').exists()).toBe(false)
    // the Images screen has its own fields, with no note
    expect(mount(FilterBar, { props: { fields: IMAGES_FIELDS, selections: { repo: ['shop/app'] } } }).find('.fpill-note').exists()).toBe(false)
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

/**
 * The namespace boxes of Scan scope (ChipsInput) wear the kit box `.set-input`: its line, fill,
 * hover wash and line, and the coral line while the input inside has focus (issue 1140, step 3.1).
 * The chip row is the box, so its input has no border of its own.
 */
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import ChipsInput from '@/components/settings/ChipsInput.vue'

describe('ChipsInput', () => {
  it('is a kit box, with no line or fill of its own', () => {
    const w = mount(ChipsInput, { props: { items: ['kube-system'] } })
    expect(w.classes()).toEqual(expect.arrayContaining(['chips', 'set-input']))
    const css = readFileSync(join(__dirname, '..', 'components/settings/ChipsInput.vue'), 'utf8').split('<style')[1]!
    const chips = css.slice(css.indexOf('\n.chips {'), css.indexOf('}', css.indexOf('\n.chips {')))
    expect(chips).not.toMatch(/border|background/)
  })

  it('adds the typed value on Enter and clears the input', async () => {
    const w = mount(ChipsInput, { props: { items: [] } })
    const input = w.get('input')
    await input.setValue('  team-a ')
    await input.trigger('keydown', { key: 'Enter' })
    expect(w.emitted('add')).toEqual([['  team-a ']])
    expect((input.element as HTMLInputElement).value).toBe('')
  })

  it('removes a chip from its own button', async () => {
    const w = mount(ChipsInput, { props: { items: ['a', 'b'] } })
    await w.get('button[aria-label="Remove b"]').trigger('click')
    expect(w.emitted('remove')).toEqual([['b']])
  })
})

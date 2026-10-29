/**
 * One text box and one dropdown (issue 1050): their look lives in base.css with every state, and
 * the kit parts that draw a box (`SettingsInput`, `UiDateTime`) wear it. The style rules test
 * refuses a copy of either rule outside base.css.
 */
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import SettingsInput from '@/components/settings/SettingsInput.vue'
import UiDateTime from '@/components/ui/UiDateTime.vue'

const base = readFileSync(join(__dirname, '..', 'styles', 'base.css'), 'utf8')

/** the declarations of one rule in base.css, by its exact selector */
function rule(selector: string): string {
  const at = base.indexOf(`\n${selector} {`)
  expect(at, `${selector} is in base.css`).toBeGreaterThan(-1)
  return base.slice(at, base.indexOf('}', at))
}

describe('the text box and the dropdown (issue 1050)', () => {
  it('the box has every state: hover wash and line, focus, keyboard focus, invalid and disabled', () => {
    expect(rule('.set-input')).toContain('border: 1px solid var(--line);')
    const hover = rule('.set-input:hover:not(:disabled)')
    expect(hover).toContain('background: var(--control-hover-bg);')
    expect(hover).toContain('border-color: var(--control-hover-line);')
    expect(rule('.set-input:focus')).toContain('border-color: var(--coral);')
    expect(rule('.set-input:focus-visible')).toContain('outline: var(--focus-ring);')
    expect(rule('.set-input--invalid')).toContain('border-color: var(--coral-d);')
    expect(rule('.set-input:disabled')).toContain('cursor: not-allowed;')
    expect(rule('.set-input--prose')).toContain('font-family: var(--font-ui);')
    expect(rule('textarea.set-input')).toContain('resize: vertical;')
  })

  it('the dropdown has the same states, and a row size for a table', () => {
    expect(rule('.set-select')).toContain('border: 1px solid var(--line);')
    const hover = rule('.set-select:hover:not(:disabled)')
    expect(hover).toContain('background: var(--control-hover-bg);')
    expect(hover).toContain('border-color: var(--control-hover-line);')
    expect(rule('.set-select:focus-visible')).toContain('outline: var(--focus-ring);')
    expect(rule('.set-select:disabled')).toContain('cursor: not-allowed;')
    expect(rule('.set-select--row')).toContain('padding: 6px 9px;')
  })

  it('SettingsInput draws the shared box, and prose and invalid add their variants', () => {
    const plain = mount(SettingsInput, { props: { modelValue: 'x' } }).find('input')
    expect(plain.classes()).toEqual(['set-input'])
    const prose = mount(SettingsInput, { props: { modelValue: 'x', prose: true, invalid: true } }).find('input')
    expect(prose.classes()).toEqual(expect.arrayContaining(['set-input', 'set-input--prose', 'set-input--invalid']))
  })

  it('UiDateTime draws the shared box for the date and the time, and marks both invalid', () => {
    const w = mount(UiDateTime, { props: { modelValue: { date: '', time: '' }, invalid: true } })
    const boxes = w.findAll('input')
    expect(boxes).toHaveLength(2)
    for (const b of boxes) expect(b.classes()).toEqual(expect.arrayContaining(['set-input', 'set-input--invalid']))
  })
})

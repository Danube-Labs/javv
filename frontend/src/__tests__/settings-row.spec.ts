/**
 * A Settings row with a wide box (`stack`) puts its hint above the box. The hint stops at 75
 * characters, a line that people can read (issue 1140, R10, operator ruling on built pictures).
 * A row with the box beside it keeps its narrow label column.
 */
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import SettingsRow from '@/components/settings/SettingsRow.vue'

const css = readFileSync(join(__dirname, '..', 'components/settings/SettingsRow.vue'), 'utf8')
function rule(selector: string): string {
  const at = css.indexOf(`\n${selector} {`)
  expect(at, `${selector} is in the CSS`).toBeGreaterThan(-1)
  return css.slice(at, css.indexOf('}', at))
}

describe('SettingsRow', () => {
  it('stops the hint of a stacked row at 75 characters', () => {
    expect(rule('.set-row-stack .set-row-label')).toContain('max-width: 75ch;')
  })

  it('keeps the label column of a row with the box beside it', () => {
    expect(rule('.set-row-label')).toContain('max-width: 340px;')
  })

  it('stack puts the row on the stacked layout', () => {
    const w = mount(SettingsRow, { props: { label: 'Namespaces', hint: 'A hint', stack: true } })
    expect(w.classes()).toContain('set-row-stack')
  })
})

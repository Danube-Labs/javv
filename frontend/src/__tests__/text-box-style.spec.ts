/**
 * One text box and one dropdown (issue 1050): their look lives in base.css with every state, and
 * the kit parts that draw a box (`SettingsInput`, `UiDateTime`) wear it. The style rules test
 * refuses a copy of either rule outside base.css. The windows draw their boxes with the kit pieces
 * `UiTextBox`, `UiTextArea` and `UiSelect`, and the search boxes with `UiSearchBox` (issue 1055).
 */
import { mount } from '@vue/test-utils'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import SettingsInput from '@/components/settings/SettingsInput.vue'
import UiDateTime from '@/components/ui/UiDateTime.vue'

const SRC = join(__dirname, '..')
const base = readFileSync(join(SRC, 'styles', 'base.css'), 'utf8')

function vueFiles(dir: string): string[] {
  return readdirSync(join(SRC, dir), { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? vueFiles(join(dir, e.name)) : e.name.endsWith('.vue') ? [join(dir, e.name)] : [],
  )
}

/** every raw text box, text area, date box and dropdown in a file's template, as its opening tag */
function rawFields(rel: string): string[] {
  const src = readFileSync(join(SRC, rel), 'utf8')
  const template = src.slice(src.indexOf('<template>'), src.lastIndexOf('</template>'))
  return [...template.matchAll(/<(input|textarea|select)\b[^>]*>/g)]
    .map((m) => m[0])
    .filter((tag) => !/type="(checkbox|radio|file)"/.test(tag))
}

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

  it('every box in a window, in the triage panel and in SettingsInput is a kit piece, never a raw field (issue 1055)', () => {
    // a raw field could wear the class and still drift in its own scoped style; a kit piece cannot.
    // rawFields leaves out the file picker of Import dashboards: a button stands in for it.
    const files = vueFiles('.')
      .filter((f) => !f.includes('__tests__') && !f.startsWith('components/ui/'))
      .filter(
        (f) =>
          /<ModalShell\b/.test(readFileSync(join(SRC, f), 'utf8')) ||
          f.endsWith('TriagePanel.vue') ||
          f.endsWith('SettingsInput.vue'),
      )
    expect(files.length).toBeGreaterThan(10)
    expect(files.flatMap((f) => rawFields(f).map((tag) => `${f}: ${tag}`))).toEqual([])
  })

  it('the search box has the hover wash and line and the coral line on focus, on the rail card too (issue 1053)', () => {
    // one rule set serves both selectors, so the rail card cannot drift from the box
    expect(rule('.search-box,\n.facet-search')).toContain('border: 1px solid var(--line);')
    const hover = rule('.search-box:hover,\n.facet-search:hover')
    expect(hover).toContain('background: var(--control-hover-bg);')
    expect(hover).toContain('border-color: var(--control-hover-line);')
    expect(rule('.search-box:focus-within,\n.facet-search:focus-within')).toContain('border-color: var(--coral);')
  })

  it('the value searches of Add filter are the kit search box (issues 1053 and 1055)', () => {
    const src = readFileSync(join(SRC, 'components/filters/FilterBar.vue'), 'utf8')
    const boxes = [...src.matchAll(/<UiSearchBox\b[\s\S]*?\/>/g)].map((m) => m[0])
    expect(boxes).toHaveLength(2)
    for (const tag of boxes) expect(tag).toContain('class="filter-vsearch"')
    expect(rawFields('components/filters/FilterBar.vue')).toEqual([])
  })

  it('the time picker, sign-in, the Inspect path box and the filter searches draw their fields with kit pieces (issue 1055)', () => {
    // Inspect keeps one raw field: the request body editor is a code panel, not a form field.
    const files: [string, number][] = [
      ['components/time-travel/GlobalTimePicker.vue', 6],
      ['views/LoginView.vue', 5],
      ['views/InspectView.vue', 1],
      ['views/FindingsView.vue', 1],
      ['views/ImagesView.vue', 1],
      ['views/ApprovalsView.vue', 1],
    ]
    const raw = files.flatMap(([f, pieces]) => {
      const src = readFileSync(join(SRC, f), 'utf8')
      expect(src.match(/<Ui(TextBox|Select|SearchBox)\b/g)?.length, `${f} draws its fields with kit pieces`).toBe(pieces)
      return rawFields(f)
        .filter((tag) => !(f === 'views/InspectView.vue' && tag.includes('class="editor"')))
        .map((tag) => `${f}: ${tag}`)
    })
    expect(raw).toEqual([])
  })
})

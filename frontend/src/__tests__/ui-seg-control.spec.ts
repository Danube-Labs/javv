/**
 * UiSegControl: the pick-one bar. Its group carries the name from `label`, so a screen reader says
 * what the buttons change; a label above the control names nothing, because `<label for>` cannot
 * name a div (issue 1011). The prop is required, so vue-tsc stops a use without it; the scan below
 * also stops an empty one.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'

import UiSegControl from '@/components/ui/UiSegControl.vue'
import { SCANNER_SWITCH_OPTS } from '@/lib/scannerLens'

const OPTIONS = [
  { value: 'half', label: 'Half' },
  { value: 'full', label: 'Full' },
] as const

const mountBar = (modelValue: 'half' | 'full') =>
  mount(UiSegControl, { props: { options: OPTIONS, modelValue, label: 'Width' } })

describe('UiSegControl', () => {
  it('gives an option its hover text when the option has a title, and no title otherwise', () => {
    const w = mount(UiSegControl, {
      props: { options: [{ value: 'a', label: 'A', title: 'More about A' }, { value: 'b', label: 'B' }], modelValue: 'a', label: 'Pick' },
    })
    const [a, b] = w.findAll('button')
    expect(a!.attributes('title')).toBe('More about A')
    expect(b!.attributes('title')).toBeUndefined()
  })

  it('the All scanners option of the scanner switch says that it adds the two scanners (issue 1140, R4)', () => {
    const all = SCANNER_SWITCH_OPTS.find((o) => o.value === 'all')!
    expect(all.title).toBe('Trivy and Grype together. A CVE that both report counts once for each.')
    expect(SCANNER_SWITCH_OPTS.filter((o) => 'title' in o)).toHaveLength(1)
  })

  it('is a group named by its label, with one button for each option, in order', () => {
    const w = mountBar('half')
    expect(w.attributes('role')).toBe('group')
    expect(w.attributes('aria-label')).toBe('Width')
    const buttons = w.findAll('button')
    expect(buttons.map((b) => b.text())).toEqual(['Half', 'Full'])
    expect(buttons.every((b) => b.attributes('type') === 'button')).toBe(true)
  })

  it('marks the picked option as pressed, and only that one', () => {
    const buttons = mountBar('full').findAll('button')
    expect(buttons.map((b) => b.attributes('aria-pressed'))).toEqual(['false', 'true'])
    expect(buttons[1]!.classes()).toContain('ui-seg-on')
  })

  it('reports the value of the pressed button', async () => {
    const w = mountBar('half')
    await w.findAll('button')[1]!.trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([['full']])
  })
})

const SRC = resolve(process.cwd(), 'src')

function vueFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return name === '__tests__' ? [] : vueFiles(p)
    return name.endsWith('.vue') ? [p] : []
  })
}

describe('every UiSegControl in the app has a name', () => {
  const uses = vueFiles(SRC).flatMap((file) =>
    [...readFileSync(file, 'utf8').matchAll(/<UiSegControl\b[^>]*>/g)].map((m) => ({
      where: relative(SRC, file),
      tag: m[0],
    })),
  )

  it('finds the uses', () => {
    expect(uses.length).toBeGreaterThan(0)
  })

  it('gives each one a label that is not empty', () => {
    const unnamed = uses
      .filter(({ tag }) => !/\slabel="[^"\s][^"]*"|\s:label="[^"]+"/.test(tag))
      .map(({ where }) => where)
    expect(unnamed).toEqual([])
  })
})

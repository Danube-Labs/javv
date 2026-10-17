/**
 * Page entry (issue 902, operator decision D2 B): the blocks of the routed page fade in and the
 * outer ones rise 6px, from base.css alone. jsdom runs no CSS animations, so this reads the rules
 * themselves: transform and opacity only, the motion tokens, zero specificity, an off switch for
 * reduced motion, and the class on the app shell's main area.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '..')
const css = readFileSync(join(SRC, 'styles/base.css'), 'utf8')
const shell = readFileSync(join(SRC, 'layouts/AppShell.vue'), 'utf8')

const block = (re: RegExp) => re.exec(css)?.[0] ?? ''

describe('page entry motion', () => {
  it('the keyframes move only opacity and translate', () => {
    const rise = block(/@keyframes page-rise \{[\s\S]*?\n\}/)
    const fade = block(/@keyframes page-fade \{[\s\S]*?\n\}/)
    expect(rise).toMatch(/opacity: 0;\s*translate: 0 6px;/)
    expect(fade).toMatch(/opacity: 0;/)
    const props = [...(rise + fade).matchAll(/^\s+([a-z-]+):/gm)].map((m) => m[1])
    expect(new Set(props)).toEqual(new Set(['opacity', 'translate']))
  })

  it('the outer blocks rise and the blocks inside them fade, on the motion tokens, without holding the end values', () => {
    expect(css).toContain(':where(.page-motion) > * > * {\n  animation: page-rise var(--dur-panel) var(--ease-out) backwards;')
    expect(css).toContain(':where(.page-motion) > * > * > * {\n  animation: page-fade var(--dur-panel) var(--ease-out) backwards;')
  })

  it('no selector of the page motion has a specificity above zero', () => {
    const selectors = [...css.matchAll(/^(.*\.page-motion.*)\{$/gm)].map((m) => m[1]!)
    expect(selectors.length).toBeGreaterThan(0)
    for (const s of selectors) expect(s.replace(/:where\([^)]*\)/g, '')).not.toMatch(/[.#[]/)
  })

  it('reduced motion turns it off', () => {
    const off = block(/@media \(prefers-reduced-motion: reduce\) \{\s*:where\(\.page-motion\)[\s\S]*?\n\}/)
    expect(off).toContain(':where(.page-motion) > * > *,')
    expect(off).toContain(':where(.page-motion) > * > * > * {')
    expect(off).toContain('animation: none;')
  })

  it('the app shell puts the class on its main area', () => {
    expect(shell).toMatch(/<main class="content page-motion"/)
  })
})

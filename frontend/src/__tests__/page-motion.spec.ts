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

/**
 * The genie motion of the four popovers (issue 1240, decision 5, operator 2026-11-17): a ruled
 * exception to DESIGN.md §5. It opens in --dur-pour (380 ms) and closes in --dur-panel, it may
 * animate clip-path next to transform and opacity, and it is the class t-pour.
 */
describe('the genie motion t-pour', () => {
  const tokens = readFileSync(join(SRC, 'styles/tokens.css'), 'utf8')
  it('its open is --dur-pour, 380 ms, a token of its own', () => {
    expect(tokens).toMatch(/--dur-pour: 380ms;/)
  })
  it('opens in --dur-pour and closes the same way back in --dur-panel, on --ease-out', () => {
    expect(css).toMatch(/\.t-pour-enter-active \{[^}]*animation: pour var\(--dur-pour\) var\(--ease-out\) both;/)
    expect(css).toMatch(/\.t-pour-leave-active \{[^}]*animation: pour var\(--dur-panel\) var\(--ease-out\) reverse both;/)
  })
  it('starts at the point that the popover gives, the tip of its arrow', () => {
    expect(css).toMatch(/\.t-pour-enter-active,\n\.t-pour-leave-active \{\n  transform-origin: var\(--pour-origin\);/)
  })
  it('the keyframes move only opacity, transform and clip-path', () => {
    const pour = block(/@keyframes pour \{[\s\S]*?\n\}/)
    const props = [...pour.matchAll(/([a-z-]+):\s/g)].map((m) => m[1])
    expect(new Set(props)).toEqual(new Set(['opacity', 'transform', 'clip-path']))
  })
  it('reduced motion turns it off', () => {
    const off = block(/@media \(prefers-reduced-motion: reduce\) \{\s*\.t-pour-enter-active[\s\S]*?\n\}/)
    expect(off).toContain('.t-pour-leave-active {')
    expect(off).toContain('animation: none;')
  })
})

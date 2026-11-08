/**
 * The strip above each Settings page that names its scope (per cluster, per scanner, organization):
 * a white card, as the other cards of Settings (issue 1127, D6 option C, operator 2026-11-07 on
 * built pictures). On --panel with a --line2 border it read as too muted.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import { SETTINGS_SECTIONS } from '@/views/settings/sections'

const css = readFileSync(join(__dirname, '..', 'views/settings/SettingsLayout.vue'), 'utf8')

function rule(selector: string): string {
  const at = css.indexOf(`\n${selector} {`)
  expect(at, `${selector} is in the CSS`).toBeGreaterThan(-1)
  return css.slice(at, css.indexOf('}', at))
}

describe('the scope strip of Settings (issue 1127)', () => {
  it('is a white card with the line and shadow of the other Settings cards', () => {
    const strip = rule('.scope-strip')
    expect(strip).toContain('background: var(--card);')
    expect(strip).toContain('border: 1px solid var(--line);')
    expect(strip).toContain('box-shadow: var(--shadow);')
  })

  it('keeps the scope color on the badge only, with no stripe', () => {
    expect(rule('.scope-strip')).not.toMatch(/border-left|var\(--sc\)/)
    expect(rule('.scope-badge')).toContain('background: var(--sc);')
  })
})

// One push token list shows the tokens of every cluster (D38), so the strip says Organization,
// not Per cluster (issue 1140, R1).
describe('the scope of the token sections', () => {
  const scopeOf = (key: string) => SETTINGS_SECTIONS.find((s) => s.key === key)?.scope
  it('Access & tokens and AI agents (MCP) are Organization', () => {
    expect(scopeOf('tokens')).toBe('org')
    expect(scopeOf('ai-agents')).toBe('org')
  })
})

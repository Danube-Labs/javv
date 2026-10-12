/**
 * The maintenance page is served while the backend is switched off (issue 675), so it must stand
 * alone: no script, nothing loaded from elsewhere. It cannot read tokens.css either, so the
 * colors it copies are checked against the tokens here.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const page = readFileSync(resolve(process.cwd(), 'public/maintenance.html'), 'utf8')
const tokens = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')

describe('public/maintenance.html', () => {
  it('runs no script and loads nothing from elsewhere', () => {
    expect(page).not.toMatch(/<script/i)
    expect(page).not.toMatch(/<link/i)
    expect(page).not.toMatch(/<img/i)
    // the inline mark fills from its own gradients, `url(#sky)`: a reference inside this file
    expect(page).not.toMatch(/url\((?!#)/i)
    expect(page).not.toMatch(/@import/i)
    expect(page).not.toMatch(/(src|href)\s*=/i)
  })

  it('draws the brand mark inline, hidden from assistive tech', () => {
    expect(page.match(/<svg[^>]*>/)![0]).toContain('aria-hidden="true"')
  })

  it('has one h1 and a title', () => {
    expect(page.match(/<h1[\s>]/g)).toHaveLength(1)
    expect(page).toMatch(/<title>[^<]+<\/title>/)
  })

  it('asks again on its own, so it leaves once the app is back', () => {
    expect(page).toMatch(/<meta http-equiv="refresh" content="60"/)
  })

  it('uses no em dash', () => {
    expect(page).not.toContain('—')
  })

  it('copies only colors that tokens.css still defines, under the same names', () => {
    const copied = [...page.matchAll(/(--[\w-]+):\s*(#[0-9a-f]{6});/g)]
    expect(copied.length).toBeGreaterThan(0)
    for (const [, name, hex] of copied) {
      expect(tokens, `${name} is no longer ${hex} in tokens.css`).toMatch(
        new RegExp(`${name}:\\s*${hex}`),
      )
    }
    // and no color outside that copied list
    // the brand mark carries its own brand colors
    const body = page.replace(/:root\s*\{[^}]*\}/, '').replace(/<svg[\s\S]*<\/svg>/, '')
    expect(body).not.toMatch(/#[0-9a-f]{3,8}\b/i)
  })

  it('names the two token families in its font stacks', () => {
    const stacks = [...page.matchAll(/font-family:\s*'([^']+)'/g)].map(([, family]) => family)
    for (const token of ['font-ui', 'font-mono']) {
      const family = tokens.match(new RegExp(`--${token}:\\s*'([^']+)'`))![1]
      expect(stacks, `--${token}`).toContain(family)
    }
  })
})

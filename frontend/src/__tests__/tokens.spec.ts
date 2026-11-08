import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import {
  CHART_ACCENT,
  CHART_PTYPE_RAMP,
  CHART_SCANNER,
  CHART_SEV,
  CHART_UI,
  SEV_COLOR,
  SEVERITIES,
  STATE_COLOR,
  STATES,
} from '@/styles/tokens'

const tokensCss = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')

describe('severity token map (D46 vocabulary)', () => {
  it('carries exactly the six canonical severities', () => {
    expect(SEVERITIES).toEqual(['critical', 'high', 'medium', 'low', 'negligible', 'unknown'])
  })

  it.each(SEVERITIES)('%s round-trips to CSS custom properties that exist', (sev) => {
    for (const part of ['fg', 'bg', 'line', 'solid'] as const) {
      expect(SEV_COLOR[sev][part]).toBe(`var(--sev-${sev}-${part})`)
      expect(tokensCss).toContain(`--sev-${sev}-${part}:`)
    }
  })

  // language A (2026-07-12): charts have their OWN escalation ramp — the -chart family
  // (critical/high == the solids; the tail recedes). Chips keep -solid.
  it.each(SEVERITIES)('CHART_SEV.%s is pinned to the same hex as the CSS -chart token', (sev) => {
    const m = tokensCss.match(new RegExp(`--sev-${sev}-chart:\\s*(#[0-9a-f]{6})`, 'i'))
    const hex = m?.[1]
    expect(hex, `--sev-${sev}-chart missing from tokens.css`).toBeDefined()
    expect(CHART_SEV[sev].toLowerCase()).toBe(hex!.toLowerCase())
  })

  it.each(['critical', 'high'] as const)('the %s chart hue stays the full-saturation solid', (sev) => {
    const m = tokensCss.match(new RegExp(`--sev-${sev}-solid:\\s*(#[0-9a-f]{6})`, 'i'))
    expect(CHART_SEV[sev].toLowerCase()).toBe(m![1]!.toLowerCase())
  })

  it('negligible is muted, never red (A-1 ruling)', () => {
    const m = tokensCss.match(/--sev-negligible-solid:\s*#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})/i)
    expect(m).not.toBeNull()
    const [r = 0, g = 0, b = 0] = (m ?? []).slice(1).map((h) => parseInt(h, 16))
    expect(r, 'negligible must not read as red').toBeLessThanOrEqual(g + 16)
    expect(r).toBeLessThanOrEqual(b + 32)
  })
})

describe('chart literals stay pinned to the CSS tokens (M9c)', () => {
  const cssHex = (name: string): string | undefined =>
    tokensCss.match(new RegExp(`${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1]?.toLowerCase()

  it('scanner series colors equal --scanner-*-fg', () => {
    expect(CHART_SCANNER.trivy.toLowerCase()).toBe(cssHex('--scanner-trivy-fg'))
    expect(CHART_SCANNER.grype.toLowerCase()).toBe(cssHex('--scanner-grype-fg'))
  })

  it('the activity-lens accent equals --slate2, not --coral (issue 1140, R8)', () => {
    expect(CHART_ACCENT.toLowerCase()).toBe(cssHex('--slate2'))
  })

  it('chart chrome literals equal their named tokens', () => {
    expect(CHART_UI.axisLine.toLowerCase()).toBe(cssHex('--line'))
    expect(CHART_UI.splitLine.toLowerCase()).toBe(cssHex('--line2'))
    expect(CHART_UI.label.toLowerCase()).toBe(cssHex('--soft'))
    expect(CHART_UI.tooltipBg.toLowerCase()).toBe(cssHex('--slate'))
    expect(CHART_UI.tooltipFg.toLowerCase()).toBe(cssHex('--side-brand-fg'))
    expect(CHART_UI.segBorder.toLowerCase()).toBe(cssHex('--card'))
  })

  it('the ptype ramp anchors on --teal (brand-info categorical, never severity)', () => {
    expect(CHART_PTYPE_RAMP[0].toLowerCase()).toBe(cssHex('--teal'))
    expect(CHART_PTYPE_RAMP.length).toBeGreaterThanOrEqual(8) // covers the 8 live ptype buckets
  })
})

/** OKLCH lightness (0 to 1) of a hex: what is left of a colour in grayscale. */
function lightness(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  return 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
}

describe('colours that must differ without hue (issue 659)', () => {
  const cssHex = (name: string): string => {
    const hex = tokensCss.match(new RegExp(`--${name}:\\s*(#[0-9a-f]{6})`, 'i'))?.[1]
    if (!hex) throw new Error(`--${name} is not a hex token in tokens.css`)
    return hex.toLowerCase()
  }
  // under this, two neighbours read as one gray (medium and low were 0.00 apart)
  const STEP = 0.04

  it('the severity chart ramp gets lighter at every level, critical to unknown', () => {
    const ramp = SEVERITIES.map((s) => lightness(CHART_SEV[s]))
    for (let i = 1; i < ramp.length; i++) {
      expect(ramp[i]! - ramp[i - 1]!, `${SEVERITIES[i - 1]} → ${SEVERITIES[i]}`).toBeGreaterThanOrEqual(STEP)
    }
  })

  it('the triage bar segments are a lightness step apart: handled, open, ack, stale', () => {
    const segs = ['triage-seg-handled', 'state-open-solid', 'triage-seg-ack', 'state-stale-line'].map((t) =>
      lightness(cssHex(t)),
    )
    for (let i = 1; i < segs.length; i++) expect(segs[i]! - segs[i - 1]!).toBeGreaterThanOrEqual(0.1)
  })

  it('the healthy and stale dots are a lightness step apart', () => {
    expect(lightness(cssHex('health-ok-dot')) - lightness(cssHex('health-degraded-dot'))).toBeGreaterThanOrEqual(0.1)
  })

  it('no status colour is a copy of a severity colour', () => {
    const all = [...tokensCss.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})\b/gi)].map((m) => [m[1]!, m[2]!.toLowerCase()] as const)
    const severity = new Map(all.filter(([n]) => n.startsWith('sev-')).map(([n, hex]) => [hex, n]))
    // --health-down-fg doubles as the app's error-text red in some 25 places; it is the one
    // copy left (critical's fg) and moving it is its own ruling, not a side effect of this test
    const KNOWN = new Set(['health-down-fg'])
    const copies = all
      .filter(([n]) => /^(state|health|sla|triage)-/.test(n) && !KNOWN.has(n) && severity.has(all.find(([x]) => x === n)![1]))
      .map(([n, hex]) => `--${n} = --${severity.get(hex)}`)
    expect(copies).toEqual([])
  })

  it('the caution amber is one set of values, whatever the token is called', () => {
    expect(cssHex('health-degraded-fg')).toBe(cssHex('hist-fg'))
    expect(cssHex('health-degraded-bg')).toBe(cssHex('hist-bg'))
    expect(cssHex('sla-tight-fg')).toBe(cssHex('hist-fg'))
  })
})

describe('state token map', () => {
  it.each(STATES)('%s round-trips to CSS custom properties that exist', (state) => {
    for (const part of ['fg', 'bg', 'line'] as const) {
      expect(STATE_COLOR[state][part]).toBe(`var(--state-${state}-${part})`)
      expect(tokensCss).toContain(`--state-${state}-${part}:`)
    }
  })
})

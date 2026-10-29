/**
 * The contrast GATE (issue #301): stylelint + the style rules test police token USAGE; this test polices
 * token VALUES. It parses tokens.css and computes WCAG ratios for every text-bearing pair the
 * design uses — a PR that darkens a bg or adds a failing chip pair breaks CI, not the operator's
 * eyes. Ruled exceptions (DESIGN.md §9: white-on-coral action chips) are listed explicitly.
 *
 * Pairs follow the DESIGN.md §2 text-color rules: --soft is the floor on every light surface;
 * prose on tints is --ink; chips/tags pair their own fg/bg; the sidebar has its own ramp.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const css = readFileSync(resolve(process.cwd(), 'src/styles/tokens.css'), 'utf8')

const TOKEN_RE = /--([\w-]+):\s*(#[0-9a-fA-F]{6}|rgba?\([^)]*\))/g
const tokens: Record<string, string> = {}
for (const m of css.matchAll(TOKEN_RE)) tokens[m[1] as string] = m[2] as string

type RGB = [number, number, number]

function parseColor(v: string): { rgb: RGB; alpha: number } {
  if (v.startsWith('#')) {
    const h = v.slice(1)
    return {
      rgb: [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB,
      alpha: 1,
    }
  }
  const parts = v
    .replace(/rgba?\(/, '')
    .replace(')', '')
    .split(',')
    .map((x) => parseFloat(x))
  return { rgb: [parts[0]!, parts[1]!, parts[2]!] as RGB, alpha: parts[3] ?? 1 }
}

/** rgba washes blend over their host surface before the ratio is computed. */
function blend(fg: string, overHex: string): RGB {
  const { rgb, alpha } = parseColor(fg)
  const base = parseColor(overHex).rgb
  return rgb.map((c, i) => Math.round(alpha * c + (1 - alpha) * (base[i] as number))) as RGB
}

function luminance([r, g, b]: RGB): number {
  const f = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function ratio(fgToken: string, bgToken: string, blendOver = '#ffffff'): number {
  const bgRaw = tokens[bgToken]
  const fgRaw = tokens[fgToken]
  if (!bgRaw || !fgRaw) throw new Error(`unknown token: ${!fgRaw ? fgToken : bgToken}`)
  const bg = bgRaw.startsWith('#') ? parseColor(bgRaw).rgb : blend(bgRaw, blendOver)
  const fg = parseColor(fgRaw).rgb // text tokens are solid by rule
  const [l1, l2] = [luminance(fg), luminance(bg)].sort((a, b) => b - a) as [number, number]
  return (l1 + 0.05) / (l2 + 0.05)
}

const AA = 4.5
/** WCAG 1.4.11 non-text contrast — the floor for a MARK or icon, which carries no glyph the
 *  4.5:1 text rule was written for. Never reach for this to excuse low-contrast text. */
const NON_TEXT = 3
const LIGHT_SURFACES = ['card', 'panel', 'bg', 'line2'] as const

describe('contrast gate — every text pair computed ≥4.5:1 (AA)', () => {
  it('text floor: --ink and --soft pass on every light surface', () => {
    for (const s of LIGHT_SURFACES) {
      expect.soft(ratio('ink', s), `ink on --${s}`).toBeGreaterThanOrEqual(AA)
      expect.soft(ratio('soft', s), `soft on --${s}`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('prose on tinted panels/banners: --ink passes on every tint bg', () => {
    // solid-dark chips carry white text, not ink prose — asserted separately below
    const WHITE_TEXT_BGS = new Set(['kev-bg', 'sla-over-bg'])
    const tints = Object.keys(tokens).filter((t) => /-(bg)$/.test(t) && !WHITE_TEXT_BGS.has(t))
    for (const t of tints) {
      expect.soft(ratio('ink', t), `ink on --${t}`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('severity chips: each fg on its own bg', () => {
    for (const sev of ['critical', 'high', 'medium', 'low', 'negligible', 'unknown']) {
      expect
        .soft(ratio(`sev-${sev}-fg`, `sev-${sev}-bg`), `sev-${sev}`)
        .toBeGreaterThanOrEqual(AA)
    }
  })

  it('state pills, scanner tags, health ramp, KEV, hist: each fg on its own bg', () => {
    for (const s of ['open', 'stale', 'ack', 'resolved', 'na', 'risk']) {
      expect.soft(ratio(`state-${s}-fg`, `state-${s}-bg`), `state-${s}`).toBeGreaterThanOrEqual(AA)
    }
    for (const sc of ['trivy', 'grype']) {
      expect
        .soft(ratio(`scanner-${sc}-fg`, `scanner-${sc}-bg`), `scanner-${sc}`)
        .toBeGreaterThanOrEqual(AA)
    }
    for (const h of ['ok', 'degraded', 'down']) {
      expect.soft(ratio(`health-${h}-fg`, `health-${h}-bg`), `health-${h}`).toBeGreaterThanOrEqual(AA)
    }
    expect.soft(ratio('kev-fg', 'kev-bg'), 'kev tag').toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('kev-fg', 'sla-over-bg'), 'sla overdue pill').toBeGreaterThanOrEqual(AA)
    // the only AA-legal SOLID sev chip (DESIGN.md §2: solid = critical-only)
    expect.soft(ratio('kev-fg', 'sev-critical-solid'), 'solid critical chip').toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('hist-fg', 'hist-bg'), 'hist control').toBeGreaterThanOrEqual(AA)
    // settings scope badges (M9e): white mono label on the scope solid
    for (const sc of ['cluster', 'scanner', 'org']) {
      expect.soft(ratio('kev-fg', `scope-${sc}`), `scope-${sc} badge`).toBeGreaterThanOrEqual(AA)
    }
    // who can see a saved item (issue 1004): the badge text on its tint
    for (const who of ['everyone', 'roles']) {
      expect.soft(ratio(`share-${who}-fg`, `share-${who}-bg`), `share-${who} badge`).toBeGreaterThanOrEqual(AA)
    }
    expect.soft(ratio('soft', 'panel'), 'share owner badge').toBeGreaterThanOrEqual(AA)
    // the primary button (issue 1004): white label on the slate fill and on its hover
    expect.soft(ratio('kev-fg', 'slate2'), 'primary button').toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('kev-fg', 'slate'), 'primary button hover').toBeGreaterThanOrEqual(AA)
    // save-bar dirty surface (M9e): the unsaved-changes message on the warm tint
    expect.soft(ratio('coral-text', 'save-dirty-bg'), 'save-bar dirty msg').toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('ink', 'save-dirty-bg'), 'save-bar dirty ink').toBeGreaterThanOrEqual(AA)
  })

  it('special text tokens on their surfaces', () => {
    for (const s of LIGHT_SURFACES) {
      expect.soft(ratio('coral-text', s), `coral-text on --${s}`).toBeGreaterThanOrEqual(AA)
      expect.soft(ratio('teal-text', s), `teal-text on --${s}`).toBeGreaterThanOrEqual(AA)
    }
    // selected-preset wash (rgba over card)
    expect
      .soft(ratio('coral-text', 'dd-on-bg', tokens['card']), 'coral-text on dd wash')
      .toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('ver-none-fg', 'card'), 'no-fix italic').toBeGreaterThanOrEqual(AA)
    expect.soft(ratio('sla-tight-fg', 'card'), 'sla tight').toBeGreaterThanOrEqual(AA)
  })

  it('value actions (issue 349 §2): text over the cell wash, marks on the chip', () => {
    // The wash is a translucent STATE LAYER, so it is asserted the only way that means
    // anything: the cell's own text still passes AA once the layer is composited on top of
    // it. Do NOT add an assertion that the wash itself clears 3:1 against the card — a hover
    // layer is meant to be subtle (Material 8%, eBay +4% per state) and would fail by design;
    // 1.4.11 governs indicators that identify a component, not hover feedback.
    expect
      .soft(ratio('ink', 'cell-act-wash', tokens['card']), 'ink over the cell wash')
      .toBeGreaterThanOrEqual(AA)
    // a hovered ROW is the other ground the same layer lands on
    expect
      .soft(ratio('ink', 'cell-act-wash', tokens['row-hover']), 'ink over the cell wash on a hovered row')
      .toBeGreaterThanOrEqual(AA)
    // the +/- bars are GRAPHICS, not glyphs, so the floor is 1.4.11's 3:1 rather than AA
    expect.soft(ratio('table-head-fg', 'slate3'), 'include mark on the chip').toBeGreaterThanOrEqual(NON_TEXT)
    expect.soft(ratio('val-act-not-fg', 'slate3'), 'exclude mark on the chip').toBeGreaterThanOrEqual(NON_TEXT)
  })

  it('window head (issue 1049): the title, the line under it and the close mark on the slate band', () => {
    // the band is --table-head-bg, which is var(--slate2); the token regex reads hex values only
    expect.soft(ratio('table-head-fg', 'slate2'), 'window title on the band').toBeGreaterThanOrEqual(AA)
    // the line under the title is the head text at 75% opacity, composited on the band
    const sub = blend('rgba(217, 226, 232, 0.75)', tokens['slate2'] as string)
    const subRatio = (luminance(sub) + 0.05) / (luminance(parseColor(tokens['slate2'] as string).rgb) + 0.05)
    expect.soft(tokens['table-head-fg'], 'the 75% line above is this token').toBe('#d9e2e8')
    expect.soft(subRatio, 'window subtitle on the band').toBeGreaterThanOrEqual(AA)
    // the close mark sits on the button's resting and hover fills, both composited on the band
    for (const fill of ['side-control-bg', 'side-control-hover-bg', 'side-control-active-bg']) {
      expect.soft(ratio('table-head-fg', fill, tokens['slate2']), `close mark on --${fill}`).toBeGreaterThanOrEqual(AA)
    }
    expect.soft(ratio('coral', 'slate2'), 'focus ring on the band').toBeGreaterThanOrEqual(NON_TEXT)
  })

  it('scanner-status lanes: the table-head text clears AA on each scanner hue', () => {
    // a lane swaps only --table-head-bg for its scanner's -fg hue; the head text token stays
    for (const scanner of ['trivy', 'grype']) {
      expect
        .soft(ratio('table-head-fg', `scanner-${scanner}-fg`), `table head on the ${scanner} lane`)
        .toBeGreaterThanOrEqual(AA)
    }
  })

  /**
   * A meter's TRACK is the scale its fill is read against, so it has to stay visible on every
   * ground the row can take. `--line2` did not: 1.03:1 against the button hover wash, so the
   * triage bars lost their scale the moment a row lit up (operator, 2026-07-28).
   *
   * HOUSE floor, not a WCAG one — say so rather than dressing it as 1.4.11. A track carries no
   * information the numbers beside it don't already state, so 3:1 would force a band dark enough
   * to fight its own fill; 1.25:1 is where a 7px band stays discernible on this palette (the
   * value that failed was 1.03, the shipped one is 1.39).
   */
  it('meter tracks stay visible on every hover ground', () => {
    const TRACK_MIN = 1.25
    expect.soft(ratio('meter-track', 'card'), 'track on the card').toBeGreaterThanOrEqual(TRACK_MIN)
    expect
      .soft(ratio('meter-track', 'control-hover-bg'), 'track on a hovered button row')
      .toBeGreaterThanOrEqual(TRACK_MIN)
    expect
      .soft(ratio('meter-track', 'row-hover'), 'track on a hovered grid row')
      .toBeGreaterThanOrEqual(TRACK_MIN)
    // issue 497 brought EpssBar onto this token, and EvidenceCard draws it on the panel inset
    expect
      .soft(ratio('meter-track', 'panel'), 'track on the panel inset')
      .toBeGreaterThanOrEqual(TRACK_MIN)
    // and it must stay QUIETER than the fill it measures, or the track reads as the value
    expect
      .soft(ratio('state-resolved-solid', 'meter-track'), 'fill against its own track')
      .toBeGreaterThanOrEqual(2)
  })

  /**
   * The FIRST row's bar overhangs onto the slate table-head band, where the normal `--slate3`
   * fill computes 1.17:1 and the control all but disappears — so that row inverts to a light
   * bar with dark marks (ruled 2026-07-28). Both readings are pinned: the inverted bar has to
   * separate from the band it sits on, and its marks have to survive on the light fill.
   */
  it('value actions on the header band (issue 349 §2): the inverted first-row bar', () => {
    // the band is `--table-head-bg`, an ALIAS of `--slate2`; this gate parses literal values,
    // so aliases never enter the token map — assert against what the alias resolves to
    const BAND = 'slate2'
    // the bar against the band it overhangs — a MARK-level floor, it carries no glyph
    expect
      .soft(ratio('table-head-fg', BAND), 'inverted bar on the head band')
      .toBeGreaterThanOrEqual(NON_TEXT)
    // the marks on that inverted fill
    expect
      .soft(ratio('slate', 'table-head-fg'), 'dark marks on the inverted bar')
      .toBeGreaterThanOrEqual(NON_TEXT)
    // and the DEFAULT fill really is illegible there — the reason the inversion exists at all,
    // asserted so nobody "simplifies" the rule away and quietly restores a 1.17:1 control
    expect(ratio('slate3', BAND)).toBeLessThan(NON_TEXT)
  })

  it('dark chrome: the sidebar text ramp on the slate', () => {
    for (const t of ['side-fg', 'side-label', 'side-credit', 'side-foot-fg', 'side-foot-dim', 'side-version', 'side-brand-fg', 'side-fg-hover', 'side-foot-strong']) {
      expect.soft(ratio(t, 'slate'), `${t} on slate`).toBeGreaterThanOrEqual(AA)
    }
  })

  it('dark chrome: the collapse toggle icon on its resting and hover fills (issue 659)', () => {
    expect
      .soft(ratio('side-fg', 'side-control-bg', tokens['slate']), 'toggle icon at rest')
      .toBeGreaterThanOrEqual(AA)
    expect
      .soft(ratio('side-fg-hover', 'side-control-hover-bg', tokens['slate']), 'toggle icon on hover')
      .toBeGreaterThanOrEqual(AA)
    expect
      .soft(ratio('side-fg-hover', 'side-control-active-bg', tokens['slate']), 'toggle icon pressed')
      .toBeGreaterThanOrEqual(AA)
    // the active nav icon is coral: a MARK beside its label, so the 3:1 floor
    expect.soft(ratio('coral', 'side-on-bg', tokens['slate']), 'active nav icon').toBeGreaterThanOrEqual(NON_TEXT)
  })

  it('documents the ruled exceptions instead of testing them', () => {
    // DESIGN.md §9: white-on-coral selected chips (tt-on) are a recorded
    // brand-contract exception (≈2.7:1) — deliberately NOT asserted here.
    expect(ratio('kev-fg', 'coral')).toBeLessThan(AA) // proves the exception is real, not stale
  })
})

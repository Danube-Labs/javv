/**
 * The style rules test (ui-foundations §Enforcement): a component that ADDS a hand-rolled color —
 * a hex/rgb literal in a .vue file or in script outside the sanctioned token modules — fails CI.
 * The baseline below may only SHRINK, never grow: fixing a violation removes its entry; adding
 * one is a build break, not a new baseline entry.
 *
 * stylelint already rejects raw colors in CSS; this catches what it can't reach — inline `style=`
 * bindings, color literals in script (chart options, dynamic styles), template attributes.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import ts from 'typescript'
import { parse as parseSfc } from 'vue/compiler-sfc'

const SRC = resolve(process.cwd(), 'src')

/** Files allowed to carry color literals — the token sources themselves. */
const SANCTIONED = new Set(['styles/tokens.css', 'styles/tokens.ts', 'theme/preset.ts'])

/** Known pre-existing violations. May only shrink. */
const BASELINE = new Set<string>([])

const COLOR_LITERAL = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory())
      return name === '__tests__' || p.endsWith('api/generated') ? [] : walk(p)
    return /\.(vue|ts|css)$/.test(name) ? [p] : []
  })
}

describe('style rules — no new hand-rolled colors', () => {
  const offenders = walk(SRC)
    .map((p) => relative(SRC, p).split('\\').join('/'))
    .filter((rel) => !SANCTIONED.has(rel))
    .filter((rel) => COLOR_LITERAL.test(readFileSync(join(SRC, rel), 'utf8')))

  it('no color literals outside the sanctioned token modules', () => {
    const added = offenders.filter((f) => !BASELINE.has(f))
    expect(
      added,
      `hand-rolled color literal(s) — use tokens.css / tokens.ts instead (ui-foundations): ${added.join(', ')}`,
    ).toEqual([])
  })

  it('baseline only shrinks (remove fixed entries)', () => {
    const stale = [...BASELINE].filter((f) => !offenders.includes(f))
    expect(stale, `fixed — delete from BASELINE: ${stale.join(', ')}`).toEqual([])
  })
})

/**
 * "System arrow everywhere" (DESIGN.md §2, operator ruling 2026-07-10; bitten twice by
 * 2026-07-11 — ECharts series, then the sidebar anchors): `cursor: pointer` is banned in app
 * code. base.css rules the arrow globally; ECharts series carry `cursor: 'default'`
 * (overview-charts.spec pins those). Nothing may opt back into the hand.
 */
describe('style rules — no pointer cursor', () => {
  it('no `cursor: pointer` anywhere in src', () => {
    const hits = walk(SRC)
      .map((p) => relative(SRC, p).split('\\').join('/'))
      .filter((rel) => /cursor:\s*['"]?pointer/.test(readFileSync(join(SRC, rel), 'utf8')))
    expect(
      hits,
      `pointer cursor(s) — the arrow is ruled app-wide (DESIGN.md §2): ${hits.join(', ')}`,
    ).toEqual([])
  })
})

/**
 * "Nothing else animates layout" (DESIGN.md §9, issue 484). Animating width/height/padding/
 * margin relayouts the page on every frame; §9 rules two deliberate exceptions — the sidebar
 * collapse rail and the header card stretch (issue 902) — and states plainly that nothing else
 * does it. That sentence was true only by luck: the triage meter had been transitioning `width`
 * since M9d and surfaced through the anti-pattern detector, not through CI. Enforced here so the
 * claim stays true on its own, for CSS transitions and for `element.animate()` from script. Test
 * files are left out: they name these patterns on purpose.
 */
describe('style rules — nothing else animates layout', () => {
  /** No /g: a stateful regex would skip files on alternate `.test()` calls. */
  const LAYOUT_TRANSITION = /transition(?:-property)?:[^;}]*\b(?:width|height|padding|margin)\b/
  /** The same from script: an `element.animate()` whose keyframes move a layout property. */
  const LAYOUT_SCRIPT_ANIMATION = /\.animate\(\s*\[[^\]]*\b(?:width|height|padding|margin)\s*:/
  /** The §9-ruled layout animations: the 226↔64px sidebar collapse rail, and the header card that
   * stretches to the right when its text gets longer (issue 902, operator decision D3 A). */
  const RULED = ['components/chrome/SideNav.vue', 'composables/useStretchWidth.ts']

  const offenders = walk(SRC)
    .map((p) => relative(SRC, p).split('\\').join('/'))
    .filter((rel) => !rel.startsWith('__tests__/'))
    .filter((rel) => {
      const source = readFileSync(join(SRC, rel), 'utf8')
      return LAYOUT_TRANSITION.test(source) || LAYOUT_SCRIPT_ANIMATION.test(source)
    })

  it('no layout animation outside the ruled sidebar rail and header card stretch', () => {
    const added = offenders.filter((f) => !RULED.includes(f))
    expect(
      added,
      `animates layout — transition transform/opacity instead (DESIGN.md §9): ${added.join(', ')}`,
    ).toEqual([])
  })

  it('each ruled exception is real, not a stale entry', () => {
    for (const ruled of RULED) {
      expect(offenders, `${ruled} no longer animates layout — drop it from RULED`).toContain(ruled)
    }
  })

  it('the script check finds a width animation and lets a transform animation pass', () => {
    expect(LAYOUT_SCRIPT_ANIMATION.test('el.animate([{ width: `${a}px` }, { width: `${b}px` }], o)')).toBe(true)
    expect(LAYOUT_SCRIPT_ANIMATION.test('el.animate([{ transform: "scaleX(0)" }, { opacity: 1 }])')).toBe(false)
  })
})

/**
 * One skeleton pulse (issue 481): `.skel` + `@keyframes skel-shimmer` live in base.css and
 * `UiSkeleton` composes them. The pulse had been re-declared in 18 files under 8 keyframe names
 * before anyone counted, so a view that grows its own shimmer fails here instead of drifting.
 */
describe('style rules — one shared skeleton pulse', () => {
  it('no shimmer keyframes outside base.css', () => {
    const hits = walk(SRC)
      .map((p) => relative(SRC, p).split('\\').join('/'))
      .filter((rel) => rel !== 'styles/base.css')
      .filter((rel) => /@keyframes\s+[\w-]*shimmer\b/.test(readFileSync(join(SRC, rel), 'utf8')))
    expect(
      hits,
      `skeleton pulse(s) outside base.css — compose UiSkeleton instead: ${hits.join(', ')}`,
    ).toEqual([])
  })
})

/**
 * One set of shared skins (issue 765): `.set-flush`, `.modal-error`, `.confirm-copy` and the
 * system line `.sys-line` with its `.sys-icon` live in base.css. Each had been copied into three
 * to five views, panels, dialogs and banners, some under other names, so a component whose styles
 * define its own copy fails here instead of drifting. The text box `.set-input` and the dropdown
 * `.set-select` joined them (issue 1050): the box had four copies, the dropdown two, and the
 * `.fld` box three, which is gone. The search box `.search-box` and its rail card `.facet-search`
 * joined too (issue 1053). Only style rules count: comments, templates and scripts are not read.
 */
describe('style rules: one shared set of skins', () => {
  it('no skin defined outside base.css', () => {
    const skin = /\.(set-flush|modal-error|confirm-copy|sys-line|sys-icon|set-input|set-select|search-box|facet-search|fld)(?![\w-])[^{};]*\{/
    const styles = (rel: string): string => {
      const source = readFileSync(join(SRC, rel), 'utf8')
      if (rel.endsWith('.css')) return source
      if (!rel.endsWith('.vue')) return ''
      return parseSfc(source).descriptor.styles.map((s) => s.content).join('\n')
    }
    const hits = walk(SRC)
      .map((p) => relative(SRC, p).split('\\').join('/'))
      .filter((rel) => rel !== 'styles/base.css')
      .filter((rel) => skin.test(withoutCssComments(styles(rel))))
    expect(hits, `skin(s) redefined outside base.css: ${hits.join(', ')}`).toEqual([])
  })
})

/**
 * "Never same-hue text on its own tint" (DESIGN.md §2, operator ruling 2026-07-09; bitten twice
 * by 2026-07-10): a rule block that pairs `color: var(--X-fg)` with `background: var(--X-bg)`
 * of the SAME hue family ships low-contrast prose. Chips/tags are the ruled exception (short
 * bold data labels with gate-tested pairs) — they live in components/chips/ or match a chip
 * selector below.
 */
const CHIP_EXEMPT = [/^components\/chips\//]
const CHIP_SELECTOR =
  // chip-class: short bold data labels with gate-tested pairs, plus the sidebar's own dark ramp
  // (incl. the table-head band — B2 ruling 2026-07-16: slate2 + parchment, ~10:1 — the
  // triage-panel head that joined the same band per the 2026-07-17 ruling, and the inspector
  // cards' panel-band that joined it 2026-07-18, and the badge of a saved card that says who can
  // see the item, ruled 2026-10-29 in issue 1004, and the window head that joined the band the
  // same day in issue 1049)
  /\.(time-range-hist|kev-tag|kev-lg|both-tag|state-opt-on|vm-fp|vm-ne|side-item|tbl|triage-head|so-head|modal-head|card-head|assignee-none|panel-band|vc-badge)\b/

describe('style rules — no same-hue text on its own tint', () => {
  const files = walk(SRC)
    .map((p) => relative(SRC, p).split('\\').join('/'))
    .filter((rel) => /\.(vue|css)$/.test(rel) && !SANCTIONED.has(rel))
    .filter((rel) => !CHIP_EXEMPT.some((re) => re.test(rel)))

  it('prose on a tinted panel uses --ink; the hue stays in icon/border/background', () => {
    const hits: string[] = []
    for (const rel of files) {
      const css = readFileSync(join(SRC, rel), 'utf8')
      // each rule block: selector { declarations }
      for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
        const selector = m[1] ?? ''
        const body = m[2] ?? ''
        if (CHIP_SELECTOR.test(selector)) continue
        const fg = body.match(/color:\s*var\(--([a-z0-9-]+)-fg\)/)
        const bg = body.match(/background(?:-color)?:\s*var\(--([a-z0-9-]+)-bg\)/)
        if (fg && bg && fg[1] === bg[1]) hits.push(`${rel} → ${selector.trim().split('\n').pop()}`)
      }
    }
    expect(
      hits,
      `same-hue fg/bg pair(s) — prose on a tint is var(--ink), hue goes to icon/border/bg (DESIGN.md §2): ${hits.join('; ')}`,
    ).toEqual([])
  })
})

/**
 * No em dashes in anything the app can show (issue 652; operator ruling 2026-10-01: every string
 * literal, developer messages included, because visible copy can't be told apart from developer
 * text mechanically). Code comments are exempt. A real parser finds the copy: Vue's for template
 * text, attributes and expressions, TypeScript's for string and template literals, so a dash in a
 * comment never trips it and a dash in a `:title` binding never slips past.
 */
const EM_DASH = '\u2014'

/** Vue template AST node types (compiler-core's NodeTypes, which compiler-sfc doesn't re-export). */
const TEXT = 2
const INTERPOLATION = 5
const ATTRIBUTE = 6
const DIRECTIVE = 7

interface TplNode {
  type: number
  content?: string | { content: string; loc: { start: { offset: number } } }
  loc: { start: { offset: number } }
  props?: { type: number; name: string; value?: { content: string }; exp?: { content: string; loc: { start: { offset: number } } }; loc: { start: { offset: number } } }[]
  children?: TplNode[]
}

interface EmDashHit {
  line: number
  where: 'template text' | 'template attribute' | 'template expression' | 'string' | 'css'
}

const lineAt = (source: string, offset: number) => source.slice(0, offset).split('\n').length

function scanCode(code: string, offset: number, source: string, where: EmDashHit['where'], hits: EmDashHit[]) {
  const sf = ts.createSourceFile('scan.ts', code, ts.ScriptTarget.Latest, true)
  const visit = (node: ts.Node) => {
    const literal =
      ts.isStringLiteralLike(node) ||
      node.kind === ts.SyntaxKind.TemplateHead ||
      node.kind === ts.SyntaxKind.TemplateMiddle ||
      node.kind === ts.SyntaxKind.TemplateTail
    if (literal && node.getText(sf).includes(EM_DASH))
      hits.push({ line: lineAt(source, offset + node.getStart(sf)), where })
    ts.forEachChild(node, visit)
  }
  visit(sf)
}

function scanTemplate(node: TplNode, source: string, hits: EmDashHit[]) {
  if (node.type === TEXT && typeof node.content === 'string' && node.content.includes(EM_DASH))
    hits.push({ line: lineAt(source, node.loc.start.offset), where: 'template text' })
  if (node.type === INTERPOLATION && typeof node.content === 'object')
    scanCode(node.content.content, node.content.loc.start.offset, source, 'template expression', hits)
  for (const prop of node.props ?? []) {
    if (prop.type === ATTRIBUTE && prop.value?.content.includes(EM_DASH))
      hits.push({ line: lineAt(source, prop.loc.start.offset), where: 'template attribute' })
    if (prop.type === DIRECTIVE && prop.exp)
      scanCode(prop.exp.content, prop.exp.loc.start.offset, source, 'template expression', hits)
  }
  for (const child of node.children ?? []) scanTemplate(child, source, hits)
}

const withoutCssComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//g, '')

/** Every em dash in `source` outside a comment, by line. */
function emDashes(source: string, kind: 'vue' | 'ts' | 'css'): EmDashHit[] {
  const hits: EmDashHit[] = []
  if (kind === 'ts') scanCode(source, 0, source, 'string', hits)
  if (kind === 'css' && withoutCssComments(source).includes(EM_DASH)) hits.push({ line: 0, where: 'css' })
  if (kind === 'vue') {
    const { descriptor } = parseSfc(source)
    const tpl = descriptor.template
    // the template AST's offsets already count from the start of the file
    if (tpl?.ast) scanTemplate(tpl.ast as unknown as TplNode, source, hits)
    for (const block of [descriptor.script, descriptor.scriptSetup])
      if (block) scanCode(block.content, block.loc.start.offset, source, 'string', hits)
    for (const style of descriptor.styles)
      if (withoutCssComments(style.content).includes(EM_DASH))
        hits.push({ line: lineAt(source, style.loc.start.offset), where: 'css' })
  }
  return hits
}

describe('style rules: the em-dash scanner itself', () => {
  const D = EM_DASH
  it('finds an em dash in template text, attributes, expressions and script strings', () => {
    const vue = [
      '<template>',
      `  <p title="a ${D} b">c ${D} d</p>`,
      `  <i :title="'e ${D} f'">{{ \`g ${D} \${h}\` }}</i>`,
      '</template>',
      '<script setup lang="ts">',
      `const s = 'i ${D} j'`,
      '</script>',
    ].join('\n')
    expect(emDashes(vue, 'vue').map((h) => `${h.line} ${h.where}`)).toEqual([
      '2 template attribute',
      '2 template text',
      '3 template expression',
      '3 template expression',
      '6 string',
    ])
  })

  it('ignores every kind of comment', () => {
    const vue = [
      '<template>',
      `  <!-- a ${D} b --><p>plain</p>`,
      '</template>',
      '<script setup lang="ts">',
      `// c ${D} d`,
      `/* e ${D} f */ const s = 'plain'`,
      '</script>',
      `<style scoped>/* g ${D} h */ .x { color: red; }</style>`,
    ].join('\n')
    expect(emDashes(vue, 'vue')).toEqual([])
    expect(emDashes(`// a ${D} b\nconst s = \`c\` /* d ${D} e */`, 'ts')).toEqual([])
    expect(emDashes(`/* a ${D} b */ .x {}`, 'css')).toEqual([])
  })

  it('finds an em dash in a .ts string and in CSS content outside comments', () => {
    expect(emDashes(`const a = 1\nconst m = "x ${D} y"`, 'ts')).toEqual([{ line: 2, where: 'string' }])
    expect(emDashes(`.x::after { content: '${D}'; }`, 'css')).toEqual([{ line: 0, where: 'css' }])
  })
})

/** Known pre-existing violations. May only shrink. */
const EM_DASH_BASELINE = new Set<string>([])

describe('style rules: no em dashes in copy', () => {
  const offenders = walk(SRC)
    .map((p) => relative(SRC, p).split('\\').join('/'))
    .map((rel) => {
      const kind = rel.endsWith('.vue') ? 'vue' : rel.endsWith('.ts') ? 'ts' : 'css'
      return { rel, hits: emDashes(readFileSync(join(SRC, rel), 'utf8'), kind) }
    })
    .filter((f) => f.hits.length > 0)

  it('no em dash outside a comment: use a colon, a full stop or a comma', () => {
    const added = offenders
      .filter((f) => !EM_DASH_BASELINE.has(f.rel))
      .map((f) => `${f.rel}:${f.hits.map((h) => h.line).join(',')}`)
    expect(added, `em dash(es) in copy (issue 652): ${added.join('; ')}`).toEqual([])
  })

  it('baseline only shrinks (remove swept files)', () => {
    const names = offenders.map((f) => f.rel)
    const stale = [...EM_DASH_BASELINE].filter((f) => !names.includes(f))
    expect(stale, `swept, delete from EM_DASH_BASELINE: ${stale.join(', ')}`).toEqual([])
  })
})

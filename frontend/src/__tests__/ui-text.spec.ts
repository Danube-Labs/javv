/**
 * The text rules test (issue 1247): the text that a template shows is in strict STE and uses the
 * term list of `development/memory-bank/docs-voice.md`. It reads the text nodes, the attributes
 * that a user reads and the string literals of the template expressions of each `.vue` file.
 * The literals of `<script>` blocks and of `.ts` modules are not read: most of them are keys,
 * classes and log events, so the slices of issue 1247 read those by hand.
 *
 * BASELINE counts the hits of each file that still has some. It may only shrink: each slice
 * removes the files that it fixes, and a new hit in any file fails the build.
 */
import { describe, expect, it } from 'vitest'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { parse as parseSfc } from 'vue/compiler-sfc'

const SRC = resolve(process.cwd(), 'src')

/** The props and attributes that hold text for the user. */
const TEXT_ATTRS = new Set([
  'title', 'placeholder', 'label', 'hint', 'aria-label', 'subtitle', 'sub', 'alt', 'summary',
  'empty', 'note', 'description', 'heading', 'header', 'text', 'message', 'tooltip', 'caption',
  'copy', 'body', 'subject',
])
const isTextAttr = (name: string) => TEXT_ATTRS.has(name) || /-(label|text)$/.test(name)

export const RULES: ReadonlyArray<readonly [string, RegExp]> = [
  ['semicolon', /;/],
  ['dash', /[\u2013\u2014]|\s--\s/],
  ['plus sign', / \+ /],
  ['(s) plural', /\(s\)/],
  ['e.g. or i.e.', /\b(e\.g|i\.e)\./i],
  ['contraction', /\b(\w+n['\u2019]t|\w+['\u2019](re|ve|ll|d|m)|(it|that|there|here|what|let|who|where)['\u2019]s)\b/i],
  ['developer word', /\b(envelopes?|payloads?|idempotent|atomically|immutable|PITs?|upserts?|GitOps|provenance|server-side|CAS|mappings?|index layout|schema v\d*|auto-\w+|\w+-wide)\b/i],
  // the term list: one name for each thing (docs-voice.md, "Terms")
  ['term: send, not push or ingest', /\b(push(es|ed|ing)?|ingests?)\b/i],
  ['term: database, not store', /\bstores?\b/i],
  ['term: Approval list, not queue', /\bqueues?\b/i],
  ['term: backend, not server', /\bservers?\b/i],
  ['term: risk acceptance, not risk accept', /\brisk[- ]accepts?\b/i],
]

/**
 * Text that the rules do not read. Each entry names its ruling: the panel titles stay (operator,
 * issue 1247), "MCP server" is a product name, the Risk-accept window keeps its title (issue
 * 1205), and an image tag is pushed to a registry, which is not a scan sent to JAVV.
 */
export const ALLOWED: ReadonlyArray<RegExp> = [
  /\bScan ingest( activity)?\b/g,
  /\bFailed ingest(s| activity)\b/g,
  /\bMCP servers?\b/g,
  /\bRisk-accept this vulnerability\b/g,
  /\bpush the same tag\b/g,
]

/** The names of the rules that a text breaks. */
export function breaks(text: string): string[] {
  let t = text.replace(/\s+/g, ' ')
  for (const a of ALLOWED) t = t.replace(a, '')
  return RULES.filter(([, re]) => re.test(t)).map(([name]) => name)
}

// a literal with only word characters is a key, a class or an enum value, not text
const literals = (expr: string) =>
  [...expr.matchAll(/'([^']*)'|`([^`]*)`/g)]
    .map((m) => (m[1] ?? m[2] ?? '').replace(/\$\{[^}]*\}/g, 'x'))
    .filter((s) => /[A-Za-z]/.test(s) && !/^[\w.-]*$/.test(s))

type Node = {
  type: number
  content?: string | { content: string }
  loc: { start: { line: number } }
  props?: Array<{
    type: number
    name: string
    value?: { content: string }
    arg?: { content: string }
    exp?: { content: string }
    loc: { start: { line: number } }
  }>
  children?: Node[]
  branches?: Node[]
}

function texts(code: string): Array<[number, string]> {
  const tpl = parseSfc(code).descriptor.template
  if (!tpl) return []
  const out: Array<[number, string]> = []
  const visit = (n: Node) => {
    if (n.type === 2 && typeof n.content === 'string') out.push([n.loc.start.line, n.content])
    if (n.type === 5 && typeof n.content === 'object')
      for (const s of literals(n.content.content)) out.push([n.loc.start.line, s])
    for (const p of n.props ?? []) {
      if (p.type === 6 && p.value && isTextAttr(p.name)) out.push([p.loc.start.line, p.value.content])
      if (p.type === 7 && p.name === 'bind' && p.arg && p.exp && isTextAttr(p.arg.content))
        for (const s of literals(p.exp.content)) out.push([p.loc.start.line, s])
    }
    for (const c of n.children ?? []) visit(c)
    for (const b of n.branches ?? []) visit(b)
  }
  visit(tpl.ast as unknown as Node)
  return out
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) return name === '__tests__' || name === 'generated' ? [] : walk(p)
    return name.endsWith('.vue') ? [p] : []
  })
}

/** Files that may keep hits, with their number of hits. Empty since issue 1247: any hit fails. */
const BASELINE: Record<string, number> = {}

describe('text rules: the rules catch what they must, and only that', () => {
  it.each([
    ['Reads work; changes are not saved.', 'semicolon'],
    ['A cluster \u2014 or a namespace', 'dash'],
    ['revoke + new', 'plus sign'],
    ['3 finding(s)', '(s) plural'],
    ['e.g. Critical KEV backlog', 'e.g. or i.e.'],
    ["Couldn't check scanner freshness", 'contraction'],
    ['JAVV doesn\u2019t decide', 'contraction'],
    ['Scanners push signed envelopes', 'developer word'],
    ['the scope auto-applies', 'developer word'],
    ['none selected = cluster-wide', 'developer word'],
    ['Scanners push their scans', 'term: send, not push or ingest'],
    ['No findings in the store yet.', 'term: database, not store'],
    ['Open the untriaged queue', 'term: Approval list, not queue'],
    ['policy-checked by the server', 'term: backend, not server'],
    ['active risk-accepts', 'term: risk acceptance, not risk accept'],
  ])('%s breaks "%s"', (text, rule) => {
    expect(breaks(text)).toContain(rule)
  })

  it.each([
    'The cluster\u2019s scanner sends its scans over HTTPS.',
    'Run now',
    'Use the MCP server',
    'Scan ingest activity',
    'Failed ingests',
    'Risk-accept this vulnerability',
    'Rebuild and push the same tag, and JAVV shows a new image.',
    'Check the backend connection.',
    'Risk accepted',
  ])('%s breaks no rule', (text) => {
    expect(breaks(text)).toEqual([])
  })

  it('reads text nodes, text attributes and the literals of their expressions', () => {
    const sfc = `<template>
  <p>One; two</p>
  <Card title="A + B" :hint="ok ? 'Reads work; or not' : 'fine'" class="a;b" />
  <span>{{ n === 1 ? 'one' : 'a finding(s) left' }}</span>
  <i :data-state="'push'" />
</template>`
    expect(texts(sfc).map(([line, t]) => [line, breaks(t)])).toEqual([
      [2, ['semicolon']],
      [3, ['plus sign']],
      [3, ['semicolon']],
      [4, ['(s) plural']],
    ])
  })
})

describe('text rules: the text of the app', () => {
  const counts: Record<string, number> = {}
  const lines: string[] = []
  for (const file of walk(SRC)) {
    const rel = relative(SRC, file).split('\\').join('/')
    for (const [line, text] of texts(readFileSync(file, 'utf8'))) {
      const hit = breaks(text)
      if (!hit.length) continue
      counts[rel] = (counts[rel] ?? 0) + hit.length
      lines.push(`${rel}:${line} ${hit.join(', ')}: "${text.replace(/\s+/g, ' ').trim()}"`)
    }
  }
  const files = Object.keys({ ...counts, ...BASELINE }).sort()

  it('no file has more hits than its baseline (docs-voice.md, "Terms" and STE)', () => {
    const grew = files.filter((f) => (counts[f] ?? 0) > (BASELINE[f] ?? 0))
    const report = lines.filter((l) => grew.some((f) => l.startsWith(`${f}:`))).join('\n')
    expect(grew, `new hits, rewrite the text:\n${report}`).toEqual([])
  })

  it('the baseline only shrinks (lower or remove the entries of fixed files)', () => {
    const shrank = files.filter((f) => (counts[f] ?? 0) < (BASELINE[f] ?? 0))
    expect(shrank, `the counts now:\n${JSON.stringify(counts, null, 2)}`).toEqual([])
  })
})

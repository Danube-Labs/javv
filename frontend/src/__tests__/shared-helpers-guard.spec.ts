/**
 * The shared script helpers stay shared (issue 1190, rows 12 to 14): the number format and the day
 * label live in lib/format.ts, and the paging of a table lives in usePagedSlice or useCursorPager.
 * A component that writes its own copy again fails here, whatever name the copy has.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = resolve(process.cwd(), 'src')

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return name === '__tests__' ? [] : sourceFiles(path)
    return /\.(vue|ts)$/.test(name) ? [path] : []
  })
}

const COPIES = [
  {
    what: 'the number format of lib/format.ts (fmt)',
    home: ['lib/format.ts'],
    body: [
      /\(\s*\w+\s*:\s*number\s*\)\s*(?::\s*string\s*)?=>\s*\w+\.toLocaleString\(\s*'en-US'\s*\)/,
      /function\s+\w+\s*\(\s*\w+\s*:\s*number\s*\)\s*(?::\s*string\s*)?\{\s*return\s+\w+\.toLocaleString\(\s*'en-US'\s*\)/,
    ],
  },
  {
    what: 'the day label of lib/format.ts (dayLabel)',
    home: ['lib/format.ts'],
    body: [
      /new Date\(\s*\w+\s*\)\.toLocaleDateString\(\s*'en-GB'\s*,\s*\{\s*day:\s*'numeric'\s*,\s*month:\s*'short'\s*\}\s*\)/,
    ],
  },
  {
    what: 'the paging of usePagedSlice or useCursorPager (setSize)',
    home: ['composables/usePagedSlice.ts', 'composables/useCursorPager.ts'],
    body: [/function\s+setSize\s*\(/, /const\s+setSize\s*=/],
  },
]

/** Each copy of a shared helper in a file outside its home, as "file: what". */
export function copiesIn(file: string, source: string): string[] {
  return COPIES.filter((c) => !c.home.includes(file) && c.body.some((re) => re.test(source))).map(
    (c) => `${file}: ${c.what}`,
  )
}

describe('the shared script helpers have no copies', () => {
  it('no file outside lib/format.ts and the paging composables has a copy', () => {
    const found = sourceFiles(SRC).flatMap((path) =>
      copiesIn(relative(SRC, path), readFileSync(path, 'utf8')),
    )
    expect(found).toEqual([])
  })

  it('finds a copy under another name, in each shape', () => {
    const planted = [
      "const count = (n: number) => n.toLocaleString('en-US')",
      "function count(n: number): string {\n  return n.toLocaleString('en-US')\n}",
      "const day = (iso: string) =>\n  new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })",
      'function setSize(next: number) {\n  size.value = next\n}',
    ]
    expect(planted.map((text) => copiesIn('components/Planted.vue', text))).toEqual([
      ['components/Planted.vue: the number format of lib/format.ts (fmt)'],
      ['components/Planted.vue: the number format of lib/format.ts (fmt)'],
      ['components/Planted.vue: the day label of lib/format.ts (dayLabel)'],
      ['components/Planted.vue: the paging of usePagedSlice or useCursorPager (setSize)'],
    ])
  })

  it('leaves the homes, and a use of the format inside a template or a sentence', () => {
    expect(copiesIn('lib/format.ts', readFileSync(join(SRC, 'lib/format.ts'), 'utf8'))).toEqual([])
    expect(copiesIn('views/X.vue', "toast.success(`${count.toLocaleString('en-US')} findings`)")).toEqual([])
    expect(copiesIn('views/X.vue', "at.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })")).toEqual([])
  })
})

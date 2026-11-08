/**
 * One close button (issue 1140, R2): a control that closes something or clears a value is
 * `UiCloseButton`. This guard fails a template that shows "×" (U+00D7), or a "✕" outside the kit
 * piece, so a new close site cannot grow a look of its own again.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parse as parseSfc } from 'vue/compiler-sfc'

const SRC = join(__dirname, '..')
function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? vueFiles(join(dir, e.name)) : e.name.endsWith('.vue') ? [join(dir, e.name)] : [],
  )
}
const templates = vueFiles(SRC).map((f) => ({
  rel: relative(SRC, f).split('\\').join('/'),
  template: parseSfc(readFileSync(f, 'utf8')).descriptor.template?.content ?? '',
}))

describe('close buttons', () => {
  it('no template shows the multiplication sign ×', () => {
    expect(templates.filter((t) => t.template.includes('×')).map((t) => t.rel)).toEqual([])
  })

  it('only UiCloseButton shows ✕', () => {
    const hits = templates.filter((t) => t.template.includes('✕')).map((t) => t.rel)
    expect(hits).toEqual(['components/ui/UiCloseButton.vue'])
  })
})

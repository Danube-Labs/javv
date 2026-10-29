/**
 * The controls of a screen head (issue 1039, operator 2026-10-29, option D): every button and
 * scanner switch there is one height, 30px, with the darker line and a 1px edge with no blur under
 * it. The kit owns the rule (`head` on UiButton and UiSegControl); this spec makes sure that each
 * head uses it, and that the rule is the ruled one.
 */
import { mount } from '@vue/test-utils'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import UiButton from '@/components/ui/UiButton.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'

const SRC = join(__dirname, '..')
const read = (rel: string) => readFileSync(join(SRC, rel), 'utf8')

function vueFiles(dir: string): string[] {
  return readdirSync(join(SRC, dir), { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? vueFiles(join(dir, e.name)) : e.name.endsWith('.vue') ? [join(dir, e.name)] : [],
  )
}

/** the markup of each screen head's action block: from its opening div to the closing div at the
 * same indent. A settings card's action slot is a span, not a screen head */
function headBlocks(src: string): string[] {
  const lines = src.split('\n')
  const blocks: string[] = []
  lines.forEach((line, i) => {
    const m = /^(\s*)<div\b[^>]*class="head-actions"/.exec(line)
    if (!m) return
    const end = lines.findIndex((l, j) => j > i && l === `${m[1]}</div>`)
    blocks.push(lines.slice(i, end).join('\n'))
  })
  return blocks
}

/** the opening tag of each kit control in a block, attributes and all */
const controls = (block: string) => [...block.matchAll(/<(UiButton|UiSegControl)\b[^>]*>/g)].map((m) => m[0])

describe('the controls of a screen head (issue 1039)', () => {
  const heads = vueFiles('views')
    .map((f) => ({ file: f, blocks: headBlocks(read(f)) }))
    .filter((v) => v.blocks.length > 0)

  it('finds the screen heads that have controls', () => {
    expect(heads.map((v) => v.file.replace(/^views\//, '')).sort()).toEqual([
      'AllClustersView.vue',
      'DashboardView.vue',
      'DashboardsView.vue',
      'ImageDetailView.vue',
      'OverviewView.vue',
    ])
  })

  it.each(['AllClustersView', 'DashboardView', 'DashboardsView', 'ImageDetailView', 'OverviewView'])(
    'each control in the head of %s is a head control',
    (name) => {
      const tags = heads.find((v) => v.file.endsWith(`${name}.vue`))!.blocks.flatMap(controls)
      expect(tags.length).toBeGreaterThan(0)
      expect(tags.filter((t) => !/\shead[\s/>]/.test(t))).toEqual([])
    },
  )

  it('a head button has the padding of the control variant, the darker line and the 1px edge', () => {
    const css = read('components/ui/UiButton.vue')
    const control = /\.ui-btn--control \{\s*padding: ([^;]+);/.exec(css)?.[1]
    expect(/\.ui-btn--head \{\s*padding: ([^;]+);/.exec(css)?.[1]).toBe(control)
    expect(css).toMatch(/\.ui-btn--head \{[^}]*box-shadow: var\(--control-edge\);/)
    expect(css).toMatch(/\.ui-btn--head:not\(\.ui-btn--primary\) \{\s*border-color: var\(--control-hover-line\);/)
  })

  it('a head switch has the same edge', () => {
    expect(read('components/ui/UiSegControl.vue')).toMatch(/\.ui-seg--head \{\s*box-shadow: var\(--control-edge\);/)
  })

  it('the edge is 1px with no blur, and the soft shadow of issue 1004 is gone', () => {
    const tokens = read('styles/tokens.css')
    expect(/--control-edge: ([^;]+);/.exec(tokens)?.[1]).toBe('0 1px 0 rgb(22 35 47 / 6%)')
    expect(tokens).not.toContain('--control-lift')
  })

  it('the head option is off unless asked for, so no other control changes', () => {
    expect(mount(UiButton, { slots: { default: 'Go' } }).classes()).not.toContain('ui-btn--head')
    expect(mount(UiButton, { props: { head: true }, slots: { default: 'Go' } }).classes()).toContain('ui-btn--head')
    const opts = [{ value: 'a', label: 'A' }]
    expect(mount(UiSegControl, { props: { options: opts, modelValue: 'a', label: 'x' } }).classes()).not.toContain('ui-seg--head')
    expect(mount(UiSegControl, { props: { options: opts, modelValue: 'a', label: 'x', head: true } }).classes()).toContain(
      'ui-seg--head',
    )
  })
})

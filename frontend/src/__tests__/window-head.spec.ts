/**
 * The head of every window (issue 1049, operator 2026-10-29): the slate band of the table heads
 * and the side panel head. The frame owns it (`ModalShell`), so this spec checks the rule there,
 * that no window restyles the head, and that the frame still closes as before.
 */
import { mount } from '@vue/test-utils'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import ModalShell from '@/components/ui/ModalShell.vue'

const SRC = join(__dirname, '..')
const read = (rel: string) => readFileSync(join(SRC, rel), 'utf8')

function vueFiles(dir: string): string[] {
  return readdirSync(join(SRC, dir), { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? vueFiles(join(dir, e.name)) : e.name.endsWith('.vue') ? [join(dir, e.name)] : [],
  )
}

/** the declarations of one rule in a file's CSS, by its exact selector */
function rule(css: string, selector: string): string {
  const at = css.indexOf(`\n${selector} {`)
  expect(at, `${selector} is in the CSS`).toBeGreaterThan(-1)
  return css.slice(at, css.indexOf('}', at))
}

describe('the window head (issue 1049)', () => {
  const shell = read('components/ui/ModalShell.vue')

  it('is the slate band of the table heads and the side panel head', () => {
    const head = rule(shell, '.modal-head')
    expect(head).toContain('background: var(--table-head-bg);')
    expect(head).toContain('color: var(--table-head-fg);')
    expect(head).not.toContain('border-bottom')
    expect(rule(read('components/ui/SlideoverShell.vue'), '.so-head')).toContain('background: var(--table-head-bg);')
  })

  it('keeps the line under the title in the register of the side panel head', () => {
    expect(rule(shell, '.modal-sub')).toContain('opacity: 0.75;')
    expect(rule(read('components/ui/SlideoverShell.vue'), '.so-sub')).toContain('opacity: 0.75;')
    expect(rule(shell, '.modal-sub')).not.toContain('color:')
  })

  it('gives the close button the ramp of a control on the slate: rest, hover, pressed and focus', () => {
    const rest = rule(shell, '.modal-close')
    expect(rest).toContain('background: var(--side-control-bg);')
    expect(rest).toContain('border: 1px solid var(--table-head-line);')
    expect(rest).toContain('color: var(--table-head-fg);')
    const hover = rule(shell, '.modal-close:hover')
    expect(hover).toContain('background: var(--side-control-hover-bg);')
    expect(hover).toContain('border-color: var(--side-label);')
    expect(rule(shell, '.modal-close:active')).toContain('background: var(--side-control-active-bg);')
    expect(rule(shell, '.modal-close:focus-visible')).toContain('outline: var(--focus-ring);')
  })

  it('has no restyle in any window, so all of them look the same', () => {
    const restyles = vueFiles('.')
      .filter((f) => !f.endsWith('ModalShell.vue'))
      .filter((f) => /<style[\s\S]*\.modal-(head|sub)\b/.test(read(f)))
    expect(restyles).toEqual([])
  })

  it('still shows the title, the line under it and the close button, and closes on the button and on Escape', async () => {
    const w = mount(ModalShell, { props: { title: 'Add a panel', subtitle: 'The panels that JAVV ships.' }, attachTo: document.body })
    expect(w.find('.modal-head h3').text()).toBe('Add a panel')
    expect(w.find('.modal-head .modal-sub').text()).toBe('The panels that JAVV ships.')
    await w.find('.modal-head .modal-close').trigger('click')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toHaveLength(2)
    w.unmount()
  })
})

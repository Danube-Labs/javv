/**
 * The footer buttons of a window (issue 1053, D2 option B): Cancel, Close or Done is `ghost`, and
 * every other footer button is `primary`, so each window closes and confirms the same way. The
 * source is read, not a mounted window, because some windows open only after a request; the
 * mounted check of one window is in edit-decision-dialog.spec.ts.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const SRC = join(__dirname, '..')

function vueFiles(dir: string): string[] {
  return readdirSync(join(SRC, dir), { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? vueFiles(join(dir, e.name)) : e.name.endsWith('.vue') ? [join(dir, e.name)] : [],
  )
}

interface FooterButton {
  file: string
  label: string
  variant: string
}

/** each UiButton in the `#actions` slot of a ModalShell, with its static variant and its text */
function footerButtons(rel: string): FooterButton[] {
  const src = readFileSync(join(SRC, rel), 'utf8')
  const out: FooterButton[] = []
  for (const slot of src.matchAll(/<template #actions>([\s\S]*?)<\/template>/g)) {
    const before = src.slice(0, slot.index)
    // the slot belongs to a window only when a <ModalShell> is open at that point
    if (before.lastIndexOf('<ModalShell') <= before.lastIndexOf('</ModalShell>')) continue
    for (const b of (slot[1] ?? '').matchAll(/<UiButton\b([\s\S]*?)>([\s\S]*?)<\/UiButton>/g)) {
      const variant = /(?<![:\w-])variant="(\w+)"/.exec(b[1] ?? '')?.[1] ?? (/:variant=/.test(b[1] ?? '') ? 'bound' : 'default')
      const label = (b[2] ?? '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim()
      out.push({ file: rel, label, variant })
    }
  }
  return out
}

const buttons = vueFiles('.')
  .filter((f) => !f.includes('__tests__') && !f.endsWith('ModalShell.vue'))
  .flatMap(footerButtons)

describe('window footer buttons (issue 1053)', () => {
  it('finds the footers of the windows', () => {
    expect(new Set(buttons.map((b) => b.file)).size).toBeGreaterThan(10)
  })

  it('every footer button is ghost or primary', () => {
    const odd = buttons.filter((b) => b.variant !== 'ghost' && b.variant !== 'primary')
    expect(odd.map((b) => `${b.file}: ${b.label} is ${b.variant}`)).toEqual([])
  })

  it('Cancel, Close and Done are ghost', () => {
    const leave = buttons.filter((b) => /^(Cancel|Close|Done)$/.test(b.label))
    expect(leave.length).toBeGreaterThan(10)
    expect(leave.filter((b) => b.variant !== 'ghost').map((b) => `${b.file}: ${b.label} is ${b.variant}`)).toEqual([])
  })
})

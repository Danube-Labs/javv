/**
 * UiCloseButton: the one "✕" of the app (issue 1140, R2, operator ruling on built pictures). A
 * required label names it for a screen reader and is its hover text. On hover it takes the kit
 * wash and line, with coral text; `dark` is the look on a slate head (issue 1049).
 */
import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

import UiCloseButton from '@/components/ui/UiCloseButton.vue'

const read = (rel: string) => readFileSync(join(__dirname, '..', rel), 'utf8')
function rule(css: string, selector: string): string {
  const at = css.indexOf(`\n${selector} {`)
  expect(at, `${selector} is in the CSS`).toBeGreaterThan(-1)
  return css.slice(at, css.indexOf('}', at))
}

describe('UiCloseButton', () => {
  it('is a button that shows ✕, named by its label, with the label as hover text', async () => {
    const w = mount(UiCloseButton, { props: { label: 'Dismiss' } })
    expect(w.element.tagName).toBe('BUTTON')
    expect(w.attributes('type')).toBe('button')
    expect(w.text()).toBe('✕')
    expect(w.attributes('aria-label')).toBe('Dismiss')
    expect(w.attributes('title')).toBe('Dismiss')
    await w.trigger('click')
    expect(w.emitted('click')).toHaveLength(1)
  })

  it('takes the dark look on a slate head and the small size in a chip or a pill', () => {
    expect(mount(UiCloseButton, { props: { label: 'Close', dark: true } }).classes()).toContain('ui-close--dark')
    expect(mount(UiCloseButton, { props: { label: 'Clear', small: true } }).classes()).toContain('ui-close--sm')
  })

  it('on hover takes the kit wash and line with coral text, a press fill and the focus ring', () => {
    const css = read('components/ui/UiCloseButton.vue')
    expect(rule(css, '.ui-close')).toContain('border: 1px solid transparent;')
    const hover = rule(css, '.ui-close:hover')
    expect(hover).toContain('background: var(--control-hover-bg);')
    expect(hover).toContain('border-color: var(--control-hover-line);')
    expect(hover).toContain('color: var(--coral-text);')
    expect(rule(css, '.ui-close:active')).toContain('background: var(--control-active-bg);')
    expect(rule(css, '.ui-close:focus-visible')).toContain('outline: var(--focus-ring);')
  })
})

describe('the close sites use it', () => {
  it.each([
    ['components/ui/ModalShell.vue', '<UiCloseButton class="modal-close" dark '],
    ['components/ui/SlideoverShell.vue', '<UiCloseButton class="so-close" dark '],
    // the popover showed the grey button of the browser: its close had no style of its own
    ['components/ui/PopoverShell.vue', '<UiCloseButton class="modal-close" label="Close"'],
    ['components/ui/ToastStack.vue', '<UiCloseButton class="toast-x" '],
    ['components/system/BackendHealthBanner.vue', '<UiCloseButton class="dismiss" '],
    ['components/chrome/NotificationBell.vue', 'class="bell-x"'],
    ['components/settings/ChipsInput.vue', '<UiCloseButton class="chip-x" small '],
    ['components/filters/FilterPill.vue', '<UiCloseButton class="fpill-x" small '],
  ])('%s', (file, use) => {
    expect(read(file)).toContain(use)
  })

  it('Clear all in the bell shows the close icon, not a "×"', () => {
    expect(read('components/chrome/NotificationBell.vue')).toContain('<AppIcon name="close" :size="12" />Clear all')
  })
})

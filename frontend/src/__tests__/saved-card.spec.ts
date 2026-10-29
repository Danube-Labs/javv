/**
 * The saved-item card of Saved views and Dashboards (issue 1004, ruled on A/B pictures of the real
 * app, 2026-10-29): the whole card opens the item through its title link, the buttons in the card
 * stay their own controls, and the card's hover never takes the color of a button's hover.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { h } from 'vue'

import SavedCard from '@/components/saved/SavedCard.vue'
import UiButton from '@/components/ui/UiButton.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/', component: { render: () => null } },
    { path: '/dashboards/:id', component: { render: () => null } },
  ],
})

function mountCard(extra: Record<string, unknown> = {}) {
  const open = vi.fn<() => void>()
  const exported = vi.fn<() => void>()
  const remove = vi.fn<() => void>()
  const w = mount(SavedCard, {
    props: { title: 'Weekly risk review', owner: 'owner lead', to: '/dashboards/abc', onOpen: open, onRemove: remove, ...extra },
    slots: { actions: () => h(UiButton, { variant: 'mini', bordered: true, onClick: exported }, () => 'Export') },
    global: { plugins: [router] },
    attachTo: document.body,
  })
  return { w, open, exported, remove }
}

const click = (el: Element, init: MouseEventInit = {}) => {
  const e = new MouseEvent('click', { bubbles: true, cancelable: true, button: 0, ...init })
  el.dispatchEvent(e)
  return e
}

describe('the whole card opens the item', () => {
  it('the title is a real link to the item, so Tab reaches it and a new tab can open it', () => {
    const { w } = mountCard()
    const a = w.get('h2 a.vc-link')
    expect(a.attributes('href')).toBe('/dashboards/abc')
    expect(a.text()).toBe('Weekly risk review')
  })

  it('a plain click opens the item through the screen once; a ctrl click is left to the browser', () => {
    const { w, open } = mountCard()
    const a = w.get('a.vc-link').element
    expect(click(a).defaultPrevented).toBe(true)
    expect(open).toHaveBeenCalledTimes(1)
    expect(click(a, { ctrlKey: true }).defaultPrevented).toBe(false)
    expect(open).toHaveBeenCalledTimes(1)
  })

  it('a button in the card does its own work and does not open the item', () => {
    const { w, open, exported, remove } = mountCard({ removeLabel: 'Delete Weekly risk review' })
    click(w.get('.vc-foot button').element)
    click(w.get('.vc-x').element)
    expect(exported).toHaveBeenCalledTimes(1)
    expect(remove).toHaveBeenCalledTimes(1)
    expect(open).not.toHaveBeenCalled()
  })

  it('has no Open button: a quiet "<label> ›" ends the footer only when the screen gives a label', () => {
    const { w } = mountCard({ openLabel: 'Open in Findings' })
    expect(w.findAll('button').map((b) => b.text())).not.toContain('Open in Findings')
    const cue = w.get('.vc-foot .vc-open')
    expect(cue.text()).toBe('Open in Findings ›')
    // the link already names the action; the cue is only a sign for the eye
    expect(cue.attributes('aria-hidden')).toBe('true')
    // Dashboards gives no label: its card opens the dashboard and needs no sign (operator, 2026-10-29)
    expect(mountCard().w.find('.vc-open').exists()).toBe(false)
  })
})

describe('the look of the card (rulings 1 and 2)', () => {
  const src = readFileSync(join(__dirname, '../components/saved/SavedCard.vue'), 'utf8')
  const rule = (selector: string) => {
    const at = src.indexOf(`${selector} {`)
    expect(at, `${selector} is in SavedCard.vue`).toBeGreaterThan(-1)
    return src.slice(at, src.indexOf('}', at))
  }

  it('on hover the card stays white: a coral border and a 1px rise, never the button hover color', () => {
    const hover = rule('.view-card:hover,\n.view-card:has(.vc-link:focus-visible)')
    expect(hover).toContain('border-color: var(--coral)')
    expect(hover).toContain('transform: translateY(-1px)')
    expect(src).not.toContain('--control-hover-bg')
  })

  it('the link covers the card, and the controls in the card sit on top of it', () => {
    expect(rule('.vc-link::after')).toContain('inset: 0')
    expect(rule('.view-card')).toContain('position: relative')
    const above = rule('.vc-badge,\n.vc-x,\n.vc-foot :slotted(.ui-btn)')
    expect(above).toContain('position: relative')
    expect(above).toContain('z-index: 1')
  })

  it('a line sits above the footer', () => {
    expect(rule('.vc-foot')).toContain('border-top: 1px solid var(--line2)')
  })
})

describe('UiButton bordered', () => {
  it('adds the darker border only when a caller asks for it', () => {
    const plain = mount(UiButton, { slots: { default: () => 'Export' } })
    const bordered = mount(UiButton, { props: { bordered: true }, slots: { default: () => 'Export' } })
    expect(plain.classes()).not.toContain('ui-btn--bordered')
    expect(bordered.classes()).toContain('ui-btn--bordered')
    const src = readFileSync(join(__dirname, '../components/ui/UiButton.vue'), 'utf8')
    expect(src).toMatch(/\.ui-btn--bordered \{\s*border-color: var\(--control-hover-line\);/)
  })
})

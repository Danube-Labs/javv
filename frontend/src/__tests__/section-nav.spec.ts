/**
 * The shared section menu (issue 341): Settings' sub-pages and the Guide's sections render the
 * same rows, so one spec pins the row contract both rely on, and Settings' scope dots keep their
 * place in the trail slot after the move out of SettingsLayout.
 */
import { flushPromises, mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import SectionNav, { type SectionNavItem } from '@/components/ui/SectionNav.vue'
import { useAuthStore } from '@/stores/auth'
import SettingsLayout from '@/views/settings/SettingsLayout.vue'
import { SETTINGS_SECTIONS } from '@/views/settings/sections'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }],
})

const ITEMS: SectionNavItem[] = [
  { key: 'one', label: 'First', icon: 'clock', to: '/a' },
  { key: 'two', label: 'Second', icon: 'list', to: { hash: '#two' } },
]

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('SectionNav', () => {
  it('renders one link per item, with its label and target', async () => {
    const w = mount(SectionNav, {
      props: { items: ITEMS, active: null, label: 'Sections' },
      global: { plugins: [router] },
    })
    await flushPromises()
    const links = w.findAll('a.snav-item')
    expect(links.map((l) => l.text())).toEqual(['First', 'Second'])
    expect(links[0]!.attributes('href')).toBe('/a')
    expect(links[1]!.attributes('href')).toContain('#two')
    expect(w.find('nav').attributes('aria-label')).toBe('Sections')
  })

  it('marks only the active row, with aria-current of the given kind', async () => {
    const w = mount(SectionNav, {
      props: { items: ITEMS, active: 'two', label: 'Sections', current: 'location' },
      global: { plugins: [router] },
    })
    await flushPromises()
    const [first, second] = w.findAll('a.snav-item')
    expect(first!.classes()).not.toContain('snav-on')
    expect(first!.attributes('aria-current')).toBeUndefined()
    expect(second!.classes()).toContain('snav-on')
    expect(second!.attributes('aria-current')).toBe('location')
  })

  it('defaults aria-current to page, for rows that open another screen', async () => {
    const w = mount(SectionNav, {
      props: { items: ITEMS, active: 'one', label: 'Sections' },
      global: { plugins: [router] },
    })
    await flushPromises()
    expect(w.find('a.snav-on').attributes('aria-current')).toBe('page')
  })

  it('renders the trail slot inside each row', async () => {
    const w = mount(SectionNav, {
      props: { items: ITEMS, active: null, label: 'Sections' },
      slots: { trail: '<template #trail="{ item }"><i class="mark">{{ item.key }}</i></template>' },
      global: { plugins: [router] },
    })
    await flushPromises()
    expect(w.findAll('a.snav-item .mark').map((m) => m.text())).toEqual(['one', 'two'])
  })

  it('renders the footer slot once, after the rows and inside the menu', async () => {
    const w = mount(SectionNav, {
      props: { items: ITEMS, active: null, label: 'Sections' },
      slots: { footer: '<p class="foot">key</p>' },
      global: { plugins: [router] },
    })
    await flushPromises()
    expect(w.findAll('nav > .foot')).toHaveLength(1)
    expect(w.find('nav').element.lastElementChild!.className).toBe('foot')
    expect(w.find('a.snav-item .foot').exists()).toBe(false)
  })
})

describe('Settings on the shared menu', () => {
  it('lists the sections the user may open, each with its scope dot, the current one active', async () => {
    const auth = useAuthStore()
    auth.user = { username: 'a', role: 'admin', capabilities: ['can_manage_settings', 'can_manage_tokens', 'can_manage_users'], must_change: false } as never
    await router.push('/settings/scanning')
    const w = mount(SettingsLayout, { global: { plugins: [router], stubs: { RouterView: true } } })
    await flushPromises()

    const allowed = SETTINGS_SECTIONS.filter((s) => auth.hasCapability(s.capability))
    const rows = w.findAll('nav[aria-label="Settings sections"] a.snav-item')
    expect(rows.map((r) => r.text())).toEqual(allowed.map((s) => s.label))
    expect(rows.map((r) => r.find('.scope-dot').attributes('data-scope'))).toEqual(allowed.map((s) => s.scope))
    expect(w.find('a.snav-on').text()).toBe('Scanning')
  })

  it('says what each scope dot means: a name on the dot, and a legend under the menu', async () => {
    const auth = useAuthStore()
    auth.user = { username: 'a', role: 'admin', capabilities: ['can_manage_settings', 'can_manage_tokens', 'can_manage_users'], must_change: false } as never
    await router.push('/settings/scanning')
    const w = mount(SettingsLayout, { global: { plugins: [router], stubs: { RouterView: true } } })
    await flushPromises()

    const dots = w.findAll('a.snav-item .scope-dot')
    expect(dots.every((d) => d.attributes('role') === 'img')).toBe(true)
    expect(dots[0]!.attributes('aria-label')).toBe('Per cluster')
    expect(dots[1]!.attributes('aria-label')).toBe('Per scanner')

    const legend = w.findAll('nav .scope-legend li')
    expect(legend.map((l) => l.text())).toEqual(['Per cluster', 'Per scanner', 'Organization'])
    expect(legend.map((l) => l.find('i').attributes('data-scope'))).toEqual(['cluster', 'scanner', 'org'])
  })

  it('leaves a scope out of the legend when no visible section has it', async () => {
    const auth = useAuthStore()
    auth.user = { username: 'a', role: 'x', capabilities: ['can_manage_tokens'], must_change: false } as never
    await router.push('/settings/tokens')
    const w = mount(SettingsLayout, { global: { plugins: [router], stubs: { RouterView: true } } })
    await flushPromises()
    // Access & tokens is per cluster and AI agents (MCP) is for the organization: no section is per scanner
    expect(w.findAll('nav .scope-legend li').map((l) => l.text())).toEqual(['Per cluster', 'Organization'])
  })
})

/** the declarations of one rule in SectionNav's CSS, by its exact selector */
function rule(selector: string): string {
  const css = readFileSync(join(__dirname, '..', 'components/ui/SectionNav.vue'), 'utf8')
  const at = css.indexOf(`\n${selector} {`)
  expect(at, `${selector} is in the CSS`).toBeGreaterThan(-1)
  return css.slice(at, css.indexOf('}', at))
}

describe('the colors of a SectionNav row (issue 1127, D4 B)', () => {
  it('washes a row on hover with the kit hover fill and line', () => {
    const hover = rule('.snav-item:hover')
    expect(hover).toContain('background: var(--control-hover-bg);')
    expect(hover).toContain('border-color: var(--control-hover-line);')
  })

  it('presses a row with the kit press fill, and its text is ink there', () => {
    const press = rule('.snav-item:active')
    expect(press).toContain('background: var(--control-active-bg);')
    expect(press).toContain('color: var(--ink);')
  })

  it('shows the selected row on the press fill with coral text, so a click ends on the color of the press', () => {
    const on = rule('.snav-on,\n.snav-on:hover')
    expect(on).toContain('background: var(--control-active-bg);')
    expect(on).toContain('color: var(--coral-text);')
  })
})

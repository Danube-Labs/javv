/**
 * The package menu of the head band (issue 1205, S1 with the dark blue head, operator ruling of
 * 2026-11-16 on built pictures; it replaces the panel M1). The package name opens a menu on the kit
 * dropdown with each package and version of this CVE on this image. A click opens the finding of
 * that package. The list stops at about nine rows and scrolls (DESIGN.md §2, no unbounded panels).
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import DetailHead from '@/components/finding/DetailHead.vue'
import type { PackageOnImage } from '@/findings/detailViewModel'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/findings/:cveId', name: 'finding', component: { template: '<div />' } },
    { path: '/images/:digest', name: 'image', component: { template: '<div />' } },
  ],
})

const primary = {
  finding_key: 'fk-1',
  cve_id: 'CVE-2026-0001',
  scanner: 'trivy',
  severity: 'HIGH',
  severity_canonical: 'high',
  state: 'open',
  package_name: 'libperl5.32',
  installed_version: '5.32.1',
  image_repo: 'docker.io/library/postgres',
  tag: '13.4',
} as never

const pk = (name: string, version = '5.32.1', scanners = ['trivy', 'grype']): PackageOnImage => ({ name, version, scanners })
const three = [pk('libperl5.32'), pk('perl', '5.32.1', ['grype']), pk('perl-base')]
const twelve = Array.from({ length: 12 }, (_, i) => pk(i === 0 ? 'libperl5.32' : `lib-${String(i).padStart(2, '0')}`))

const wrappers: VueWrapper[] = []
afterEach(() => {
  for (const w of wrappers.splice(0)) w.unmount()
  document.body.innerHTML = ''
})
beforeEach(() => {
  setActivePinia(createPinia())
  // jsdom has no scrollIntoView; every browser has it
  Element.prototype.scrollIntoView = () => {}
})

async function head(packages: PackageOnImage[], packagesCut = false, packageName = 'libperl5.32') {
  await router.push('/findings/CVE-2026-0001?digest=sha256:abc&scanner=trivy&pkg=libperl5.32&ver=5.32.1')
  const w = mount(DetailHead, {
    props: {
      cveId: 'CVE-2026-0001',
      primary: { ...(primary as object), package_name: packageName } as never,
      digest: 'sha256:abc',
      kev: false,
      disagrees: false,
      epss: null,
      packages,
      packagesCut,
    },
    global: { plugins: [router] },
    attachTo: document.body,
  })
  wrappers.push(w)
  return w
}
const pkBtn = (w: VueWrapper) => w.find('button.pk-btn')
async function open(w: VueWrapper) {
  await pkBtn(w).trigger('click')
  await flushPromises()
  return w.find('.pk-menu')
}
const rowNames = (w: VueWrapper) => w.findAll('.pk-row .pk-name').map((n) => n.text())

describe('the package menu of the head band (issue 1205, S1)', () => {
  it('one package on this image: the name is plain text, with no menu', async () => {
    const w = await head([pk('libperl5.32')])
    expect(pkBtn(w).exists()).toBe(false)
    expect(w.text()).toContain('libperl5.32')
  })

  it('a refused read gives no packages: the name is plain text', async () => {
    const w = await head([])
    expect(pkBtn(w).exists()).toBe(false)
    expect(w.text()).toContain('libperl5.32')
  })

  it('more packages: the name is a button with the count on this image', async () => {
    const w = await head(three)
    expect(pkBtn(w).text()).toContain('libperl5.32')
    expect(pkBtn(w).text()).toContain('3 on this image')
    expect(pkBtn(w).attributes('aria-expanded')).toBe('false')
  })

  it('a cut list: the count says that there are more', async () => {
    const w = await head(three, true)
    expect(pkBtn(w).text()).toContain('3+ on this image')
  })

  it('opens a menu on the kit dropdown with the dark blue head: title, count, image, close button', async () => {
    const w = await head(three)
    const menu = await open(w)
    expect(menu.exists()).toBe(true)
    expect(menu.classes()).toContain('dd-menu')
    // a menu holds no form field (Primer), and this one has a filter box: it is a dialog, as SelectPanel
    expect(menu.attributes('role')).toBe('dialog')
    expect(menu.attributes('aria-label')).toBe('Packages with this vulnerability')
    expect(menu.find('.pk-head .pk-title').text()).toBe('Packages with this vulnerability · 3')
    expect(menu.find('.pk-head .pk-img').text()).toBe('docker.io/library/postgres:13.4')
    expect(menu.find('.pk-head .ui-close').classes()).toContain('ui-close--dark')
    expect(pkBtn(w).attributes('aria-expanded')).toBe('true')
  })

  it('each row has the package, its version and the scanners that found it', async () => {
    const w = await head(three)
    await open(w)
    expect(rowNames(w)).toEqual(['libperl5.32', 'perl', 'perl-base'])
    const perl = w.findAll('.pk-row')[1]!
    expect(perl.find('.pk-ver').text()).toBe('5.32.1')
    expect(perl.findAll('.scanner-tag').map((t) => t.text().toLowerCase())).toEqual(['grype'])
  })

  it('the current package is marked, and is not a link', async () => {
    const w = await head(three)
    await open(w)
    const on = w.find('.pk-row.on')
    expect(on.element.tagName).toBe('SPAN')
    expect(on.attributes('aria-current')).toBe('true')
    expect(on.find('.pk-name').text()).toBe('libperl5.32')
  })

  it('a click on a package opens the finding of that package and version, and closes the menu', async () => {
    const w = await head(three)
    await open(w)
    const link = w.findAll('a.pk-row').find((a) => a.find('.pk-name').text() === 'perl-base')!
    expect(link.attributes('href')).toBe(
      '/findings/CVE-2026-0001?digest=sha256:abc&scanner=trivy&pkg=perl-base&ver=5.32.1',
    )
    await link.trigger('click')
    await flushPromises()
    expect(w.find('.pk-menu').exists()).toBe(false)
  })

  it('the close button and Escape close the menu', async () => {
    const w = await head(three)
    await open(w)
    await w.find('.pk-head .ui-close').trigger('click')
    await flushPromises()
    expect(w.find('.pk-menu').exists()).toBe(false)
    await open(w)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(w.find('.pk-menu').exists()).toBe(false)
  })

  it('8 packages or fewer: no filter box, and the focus goes to the first link', async () => {
    const w = await head(three)
    await open(w)
    expect(w.find('.pk-menu .search-box').exists()).toBe(false)
    expect(document.activeElement?.textContent).toContain('perl')
    expect((document.activeElement as HTMLElement).classList).toContain('pk-row')
  })

  it('more than 8 packages: a filter box with the focus, which narrows the list', async () => {
    const w = await head(twelve)
    await open(w)
    const input = w.find('.pk-menu .search-box input')
    expect(input.exists()).toBe(true)
    expect(document.activeElement).toBe(input.element)
    await input.setValue('lib-1')
    expect(rowNames(w)).toEqual(['lib-10', 'lib-11'])
  })

  it('a filter with no match says so', async () => {
    const w = await head(twelve)
    await open(w)
    await w.find('.pk-menu .search-box input').setValue('zzz')
    expect(rowNames(w)).toEqual([])
    expect(w.find('.pk-menu .empty-note').text()).toBe('No package matches.')
  })

  it('the arrow keys move the focus from the filter box through the links and back', async () => {
    const w = await head(twelve)
    await open(w)
    const input = w.find('.pk-menu .search-box input')
    await input.trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement?.querySelector('.pk-name')?.textContent).toBe('lib-01')
    await w.find('.pk-list').trigger('keydown', { key: 'ArrowDown' })
    expect(document.activeElement?.querySelector('.pk-name')?.textContent).toBe('lib-02')
    await w.find('.pk-list').trigger('keydown', { key: 'ArrowUp' })
    await w.find('.pk-list').trigger('keydown', { key: 'ArrowUp' })
    expect(document.activeElement).toBe(input.element)
  })

  it('on open, the list scrolls the current package into view, so a current row low in the list shows', async () => {
    const seen: string[] = []
    // a stub records the row that the menu scrolls to
    const stub = vi.fn<(this: HTMLElement) => void>(function (this: HTMLElement) {
      seen.push(this.querySelector('.pk-name')?.textContent ?? '')
    })
    Element.prototype.scrollIntoView = stub
    const w = await head(twelve)
    await open(w)
    expect(seen).toEqual(['libperl5.32'])
  })

  it('a cut list ends with a line that says how many packages the menu shows', async () => {
    const w = await head(three, true)
    await open(w)
    // the read holds the first findings in its own order, not the first packages by name
    expect(w.find('.pk-menu .cap-note').text()).toBe('This menu shows 3 packages. The image has more.')
  })
})

/**
 * A long package name stays in its fact (issue 1229, operator rulings of 2026-11-16 on built
 * pictures: B1, M1, and the plain name of one package too). The name takes the free space and ends
 * with an ellipsis, the count and the chevron keep one line, and the full name is the hover text.
 * jsdom has no layout, so the style rules are read from the source; a browser probe measured the
 * widths (tmp/screenshots/1229).
 */
const LONG = 'go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc'

/** The declarations of `selector` in the style block of a component, as `property: value`. */
function declarations(file: string, selector: string): Record<string, string> {
  const source = readFileSync(resolve(process.cwd(), 'src/components/finding', file), 'utf8')
  const css = (/<style[^>]*>([\s\S]*?)<\/style>/.exec(source)?.[1] ?? '').replace(/\/\*[\s\S]*?\*\//g, '')
  const out: Record<string, string> = {}
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!(m[1] ?? '').split(',').map((s) => s.trim()).includes(selector)) continue
    for (const d of (m[2] ?? '').split(';')) {
      const [k, ...v] = d.split(':')
      if (k?.trim()) out[k.trim()] = v.join(':').trim()
    }
  }
  return out
}

describe('a long package name stays in the head band (issue 1229)', () => {
  it('the button has the full name as its hover text', async () => {
    const w = await head([pk(LONG), pk('perl')], false, LONG)
    expect(pkBtn(w).attributes('title')).toBe(LONG)
    expect(pkBtn(w).find('.pk-btn-name').text()).toBe(LONG)
  })

  it('the button stays in its fact: the name ends with an ellipsis, the count and the chevron keep one line', () => {
    expect(declarations('DetailHead.vue', '.fact')).toMatchObject({ 'min-width': '0', 'max-width': '100%' })
    expect(declarations('PackageMenu.vue', '.pk-dd')).toMatchObject({ 'max-width': '100%' })
    // the button sits 8px to the left of its fact (margin-left: -8px), so it may be 8px wider
    expect(declarations('PackageMenu.vue', '.pk-btn')).toMatchObject({ 'max-width': 'calc(100% + 8px)', 'margin-left': '-8px' })
    expect(declarations('PackageMenu.vue', '.pk-btn-name')).toMatchObject({
      'min-width': '0',
      overflow: 'hidden',
      'text-overflow': 'ellipsis',
      'white-space': 'nowrap',
    })
    expect(declarations('PackageMenu.vue', '.pk-count')).toMatchObject({ flex: 'none', 'white-space': 'nowrap' })
    expect(declarations('PackageMenu.vue', '.pk-chev')).toMatchObject({ flex: 'none' })
  })

  it('each row of the menu has the full name of its package as its hover text', async () => {
    const w = await head([pk(LONG), pk('perl')], false, LONG)
    await open(w)
    expect(w.findAll('.pk-row .pk-name').map((n) => n.attributes('title'))).toEqual([LONG, 'perl'])
  })

  it('one package: the plain name keeps one line, ends with an ellipsis and has the full name as its hover text', async () => {
    const w = await head([pk(LONG)], false, LONG)
    const name = w.find('.fact-val.fact-cut')
    expect(name.text()).toBe(LONG)
    expect(name.attributes('title')).toBe(LONG)
    expect(declarations('DetailHead.vue', '.fact-cut')).toMatchObject({
      overflow: 'hidden',
      'text-overflow': 'ellipsis',
      'white-space': 'nowrap',
    })
  })
})

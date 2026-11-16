/**
 * The package menu of the head band (issue 1205, S1 with the dark blue head, operator ruling of
 * 2026-11-16 on built pictures; it replaces the panel M1). The package name opens a menu on the kit
 * dropdown with each package and version of this CVE on this image. A click opens the finding of
 * that package. The list stops at about nine rows and scrolls (DESIGN.md §2, no unbounded panels).
 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
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
beforeEach(() => setActivePinia(createPinia()))

async function head(packages: PackageOnImage[], packagesCut = false) {
  await router.push('/findings/CVE-2026-0001?digest=sha256:abc&scanner=trivy&pkg=libperl5.32&ver=5.32.1')
  const w = mount(DetailHead, {
    props: { cveId: 'CVE-2026-0001', primary, digest: 'sha256:abc', kev: false, disagrees: false, epss: null, packages, packagesCut },
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
    expect(menu.attributes('aria-label')).toBe('Packages with this CVE')
    expect(menu.find('.pk-head .pk-title').text()).toBe('Packages with this CVE · 3')
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

  it('a cut list ends with a line that says how many packages the menu shows', async () => {
    const w = await head(three, true)
    await open(w)
    expect(w.find('.pk-menu .cap-note').text()).toBe('This menu shows the first 3 packages.')
  })
})

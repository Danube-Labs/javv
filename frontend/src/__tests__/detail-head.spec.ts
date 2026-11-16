/**
 * The package menu of the head band (issue 1205, P1 with the look M1, on built pictures; the dark
 * head of a window, operator 2026-11-16): the package name opens a panel with each package of
 * this CVE on this image, and a click opens the finding of that package.
 */
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import DetailHead from '@/components/finding/DetailHead.vue'

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

const wrappers: VueWrapper[] = []
afterEach(() => {
  for (const w of wrappers.splice(0)) w.unmount()
  document.body.innerHTML = ''
})
beforeEach(() => setActivePinia(createPinia()))

async function head(otherPackages: string[]) {
  await router.push('/findings/CVE-2026-0001?digest=sha256:abc&scanner=trivy&pkg=libperl5.32&ver=5.32.1')
  const w = mount(DetailHead, {
    props: {
      cveId: 'CVE-2026-0001',
      primary,
      digest: 'sha256:abc',
      kev: false,
      disagrees: false,
      epss: null,
      packages: ['libperl5.32', ...otherPackages].map((name) => ({ name, version: '5.32.1', scanners: ['trivy'] })),
      packagesCut: false,
    },
    global: { plugins: [router] },
    attachTo: document.body,
  })
  wrappers.push(w)
  return w
}
const pkBtn = (w: VueWrapper) => w.find('button.pk-btn')

describe('the package menu of the head band (issue 1205)', () => {
  it('one package on this image: the name is plain text, with no menu', async () => {
    const w = await head([])
    expect(pkBtn(w).exists()).toBe(false)
    expect(w.text()).toContain('libperl5.32')
  })

  it('more packages: the name is a button with the count on this image', async () => {
    const w = await head(['perl', 'perl-base', 'perl-modules-5.32'])
    expect(pkBtn(w).text()).toContain('libperl5.32')
    expect(pkBtn(w).text()).toContain('4 on this image')
    expect(pkBtn(w).attributes('aria-expanded')).toBe('false')
  })

  it('opens a panel with the dark head, the image, and each package; the current one is checked', async () => {
    const w = await head(['perl', 'perl-base'])
    await pkBtn(w).trigger('click')
    await flushPromises()
    const pop = w.find('.pop')
    expect(pop.exists()).toBe(true)
    expect(pop.find('.pop-head').classes()).toContain('pop-head--band')
    expect(pop.attributes('aria-label')).toBe('Packages with this CVE: docker.io/library/postgres:13.4')
    expect(pop.findAll('.m-item').map((i) => i.text())).toEqual(['libperl5.32', 'perl', 'perl-base'])
    expect(pop.find('.m-on').element.tagName).toBe('SPAN') // the current package is not a link
    expect(pkBtn(w).attributes('aria-expanded')).toBe('true')
  })

  it('a click on a package opens its finding on this image and closes the panel', async () => {
    const w = await head(['perl', 'perl-base'])
    await pkBtn(w).trigger('click')
    await flushPromises()
    const link = w.findAll('.pop a.m-item').find((a) => a.text() === 'perl-base')!
    expect(link.attributes('href')).toBe('/findings/CVE-2026-0001?digest=sha256:abc&scanner=trivy&pkg=perl-base')
    await link.trigger('click')
    await flushPromises()
    expect(w.find('.pop').exists()).toBe(false)
  })
})

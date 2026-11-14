/**
 * Affected components, the Paths column (issue 1077, D3): the number of paths of each finding of
 * a row, and a row with a path opens to list them. The paths of the two scanners stay apart.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AffectedCard from '@/components/finding/AffectedCard.vue'
import FindingPaths from '@/components/finding/FindingPaths.vue'
import type { AffectedComponentRow } from '@/findings/detailViewModel'

const comp = (over: Partial<AffectedComponentRow>): AffectedComponentRow => ({
  image: 'docker.io/rancher/local-path-provisioner:v0.0.36',
  packageName: 'stdlib',
  current: 'v1.26.3',
  fixed: '1.26.10',
  namespaces: ['kube-system'],
  scanners: ['trivy'],
  paths: [],
  ...over,
})

const trivy11 = {
  scanner: 'trivy',
  digest: 'sha256:aaa',
  total: 11,
  paths: ['/usr/bin/local-path-provisioner', '/usr/local/go/bin/go'],
}

const mountCard = (affected: AffectedComponentRow[]) =>
  mount(AffectedCard, { props: { affected, truncated: false } })

const cells = (w: ReturnType<typeof mountCard>, row = 0) =>
  w.findAll('tbody tr')[row]!.findAll('td').map((td) => td.text())

describe('AffectedCard Paths column (issue 1077)', () => {
  it('the head has Paths before Scanners', () => {
    const heads = mountCard([comp({})]).findAll('th').map((th) => th.text())
    expect(heads).toEqual(['Image', 'Namespace', 'Package', 'Current', 'Fixed', 'Paths', 'Scanners'])
  })

  it('a row with paths has a button with the count; it opens and closes the list under the row', async () => {
    const w = mountCard([comp({ paths: [trivy11] })])
    const btn = w.find('button.paths-btn')
    expect(btn.text()).toBe('11 paths')
    expect(btn.attributes('aria-expanded')).toBe('false')
    expect(btn.attributes('aria-label')).toBe('Paths: Trivy 11. Show the paths')
    expect(w.findComponent(FindingPaths).exists()).toBe(false)

    await btn.trigger('click')
    expect(btn.attributes('aria-expanded')).toBe('true')
    const panel = w.find(`#${btn.attributes('aria-controls')}`)
    expect(panel.exists()).toBe(true)
    expect(panel.findAll('li').map((li) => li.text())).toEqual(trivy11.paths)
    expect(w.findComponent(FindingPaths).props()).toMatchObject({ packageName: 'stdlib', version: 'v1.26.3' })

    await btn.trigger('click')
    expect(btn.attributes('aria-expanded')).toBe('false')
    expect(w.findComponent(FindingPaths).exists()).toBe(false)
  })

  it('a row with one path opens too: else nobody sees that file', () => {
    const w = mountCard([comp({ paths: [{ scanner: 'grype', digest: 'sha256:a', total: 1, paths: ['/usr/local/go/bin/go'] }] })])
    expect(w.find('button.paths-btn').text()).toBe('1 path')
  })

  it('a row of two scanners shows one number for each, in the order of the Scanners column', () => {
    const w = mountCard([
      comp({
        scanners: ['trivy', 'grype'],
        paths: [
          { scanner: 'trivy', digest: 'sha256:a', total: 0, paths: [] },
          { scanner: 'grype', digest: 'sha256:a', total: 5, paths: ['/var/lib/dpkg/status'] },
        ],
      }),
    ])
    expect(w.find('button.paths-btn').text()).toBe('0 · 5')
    expect(w.find('button.paths-btn').attributes('title')).toBe('Trivy: the scanner gave no path. Grype: 5 paths.')
  })

  it('a row with no path to show has no button: "0 paths", or "-" when the scan sent none', () => {
    const w = mountCard([
      comp({ image: 'a:1', paths: [{ scanner: 'trivy', digest: 'sha256:a', total: 0, paths: [] }] }),
      comp({ image: 'b:1', paths: [{ scanner: 'trivy', digest: 'sha256:b', total: null, paths: [] }] }),
    ])
    expect(w.find('button.paths-btn').exists()).toBe(false)
    expect(cells(w, 0)[5]).toBe('0 paths')
    expect(cells(w, 1)[5]).toBe('-')
    expect(w.findAll('.paths-none')[1]!.attributes('title')).toBe('Trivy: this scan did not report paths.')
  })

  it('a new read closes the rows that were open', async () => {
    const w = mountCard([comp({ paths: [trivy11] })])
    await w.find('button.paths-btn').trigger('click')
    expect(w.findComponent(FindingPaths).exists()).toBe(true)
    await w.setProps({ affected: [comp({ paths: [trivy11] })] })
    expect(w.findComponent(FindingPaths).exists()).toBe(false)
  })

  it('the empty and refused rows span all seven columns', () => {
    expect(mountCard([]).find('td.empty-row').attributes('colspan')).toBe('7')
  })
})

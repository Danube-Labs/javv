/**
 * A digest-pinned image has no tag anywhere in Kubernetes (issue 817): the pod names
 * `repo@sha256:…`, and the backend stores an empty tag. Its Tag cell shows the empty-value dash
 * (issue 652) and says why, instead of an empty cell.
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import ImagesTable from '@/components/images/ImagesTable.vue'
import type { ImageRow } from '@/stores/images'

const row = (tag: string, image_digest: string): ImageRow => ({
  image_digest,
  image_repo: 'docker.io/library/nginx',
  tag,
  namespaces: ['web'],
  scanners: ['trivy'],
  crit: 0,
  high: 0,
  med: 0,
  low: 0,
  negligible: 0,
  unknown: 0,
  total: 0,
  fixable: 0,
  replicas: 1,
  '@timestamp': '2026-10-11T10:00:00Z',
})

function tagCells(rows: ImageRow[]) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/:any(.*)*', component: { template: '<div />' } }] })
  const w = mount(ImagesTable, {
    props: { rows, sort: null, order: 'desc', loading: false, filtered: false, hidden: new Set(['namespace', 'replicas', 'vulns', 'mixTrivy', 'mixGrype', 'seen']) },
    global: { plugins: [router] },
  })
  return w.findAll('tbody tr').map((tr) => tr.findAll('td')[1]!)
}

beforeEach(() => setActivePinia(createPinia()))

describe('the Tag cell', () => {
  it('shows the tag when the pod names one', () => {
    const [cell] = tagCells([row('1.27', 'sha256:' + 'a'.repeat(64))])
    expect(cell!.text()).toContain('1.27')
    expect(cell!.find('.muted-dash').exists()).toBe(false)
  })

  it('shows the dash and why when the image is pinned by digest', () => {
    const [cell] = tagCells([row('', 'sha256:' + 'b'.repeat(64))])
    const dash = cell!.get('.muted-dash')
    expect(dash.text()).toBe('-')
    expect(dash.attributes('title')).toBe('Pinned by digest: the pod names no tag.')
  })
})

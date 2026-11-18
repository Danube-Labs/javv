import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import UiSkeleton from '@/components/ui/UiSkeleton.vue'

describe('UiSkeleton', () => {
  it('wears the shared pulse class so the animation can only be defined once', () => {
    expect(mount(UiSkeleton, { props: { height: 96 } }).classes()).toContain('skel')
  })

  it('takes height as pixels or a raw CSS length', () => {
    expect(mount(UiSkeleton, { props: { height: 300 } }).attributes('style')).toBe('height: 300px;')
    expect(mount(UiSkeleton, { props: { height: '50%' } }).attributes('style')).toBe('height: 50%;')
  })

  it('carries the small radius only when asked', () => {
    expect(mount(UiSkeleton, { props: { height: 22 } }).classes()).not.toContain('skel--sm')
    expect(mount(UiSkeleton, { props: { height: 22, radius: 'sm' } }).classes()).toContain(
      'skel--sm',
    )
  })

  it('announces itself only when it is its own loading region', () => {
    const own = mount(UiSkeleton, { props: { height: 84, label: 'Loading the scans' } })
    expect(own.attributes('aria-busy')).toBe('true')
    expect(own.attributes('aria-label')).toBe('Loading the scans')

    // inside a labelled group the wrapper announces; the children must stay silent
    const child = mount(UiSkeleton, { props: { height: 34 } })
    expect(child.attributes('aria-busy')).toBeUndefined()
    expect(child.attributes('aria-label')).toBeUndefined()
  })
})

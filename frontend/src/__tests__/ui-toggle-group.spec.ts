/**
 * UiToggleGroup: a row of buttons where each one turns its value on or off, independently of the
 * others (the scan scope's owner kinds, issue 891). The parent owns the list; the group reports
 * which value the user pressed.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import UiToggleGroup from '@/components/ui/UiToggleGroup.vue'

const OPTIONS = [
  { value: 'ReplicaSet', label: 'Deployment pods', detail: 'ReplicaSet' },
  { value: 'Job', label: 'Job and CronJob pods', detail: 'Job' },
  { value: 'DaemonSet', label: 'DaemonSet pods' },
] as const

const mountGroup = (selected: string[]) =>
  mount(UiToggleGroup, { props: { options: OPTIONS, selected, label: 'Skip workload kinds' } })

describe('UiToggleGroup', () => {
  it('is a named group with one button for each option, in order', () => {
    const w = mountGroup([])
    expect(w.attributes('role')).toBe('group')
    expect(w.attributes('aria-label')).toBe('Skip workload kinds')
    const buttons = w.findAll('button')
    expect(buttons.map((b) => b.find('.ui-tg-label').text())).toEqual([
      'Deployment pods',
      'Job and CronJob pods',
      'DaemonSet pods',
    ])
    expect(buttons.every((b) => b.attributes('type') === 'button')).toBe(true)
  })

  it('shows the detail only for an option that has one', () => {
    const buttons = mountGroup([]).findAll('button')
    expect(buttons[0]!.find('.ui-tg-detail').text()).toBe('ReplicaSet')
    expect(buttons[2]!.find('.ui-tg-detail').exists()).toBe(false)
  })

  it('marks each selected value as pressed, and only those', () => {
    const buttons = mountGroup(['Job']).findAll('button')
    expect(buttons.map((b) => b.attributes('aria-pressed'))).toEqual(['false', 'true', 'false'])
    expect(buttons[1]!.classes()).toContain('ui-tg-on')
    expect(buttons[0]!.classes()).not.toContain('ui-tg-on')
  })

  it('reports the value of the pressed button, on or off', async () => {
    const w = mountGroup(['Job'])
    await w.findAll('button')[0]!.trigger('click')
    await w.findAll('button')[1]!.trigger('click')
    expect(w.emitted('toggle')).toEqual([['ReplicaSet'], ['Job']])
  })
})

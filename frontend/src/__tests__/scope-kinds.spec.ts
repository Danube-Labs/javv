/**
 * The owner-kind buttons of the scan scope (issue 891): the saved `ignore_kinds` list splits into
 * the four buttons and the typed values, and a typed value that matches no pod gets a note.
 */
import { describe, expect, it } from 'vitest'

import { KIND_BUTTONS, kindNote, splitKinds, toggleKind } from '@/views/settings/scopeKinds'

describe('KIND_BUTTONS', () => {
  it('saves the owner kind that the scanner compares, not the workload name', () => {
    expect(KIND_BUTTONS.map((b) => [b.label, b.kind])).toEqual([
      ['Deployment pods', 'ReplicaSet'],
      ['DaemonSet pods', 'DaemonSet'],
      ['StatefulSet pods', 'StatefulSet'],
      ['Job and CronJob pods', 'Job'],
    ])
  })
})

describe('splitKinds', () => {
  it('puts the four known kinds on the buttons and keeps the rest typed, in saved order', () => {
    const { selected, typed } = splitKinds(['Cluster', 'Job', 'CronJob', 'ReplicaSet', 'job'])
    expect([...selected].sort()).toEqual(['Job', 'ReplicaSet'])
    expect(typed).toEqual(['Cluster', 'CronJob', 'job'])
  })

  it('gives no selection and no typed values for an empty list', () => {
    const { selected, typed } = splitKinds([])
    expect(selected.size).toBe(0)
    expect(typed).toEqual([])
  })
})

describe('toggleKind', () => {
  it('adds a kind that is off and removes a kind that is on, and keeps the typed values', () => {
    const on = toggleKind(['Cluster'], 'Job')
    expect(on).toEqual(['Cluster', 'Job'])
    expect(toggleKind(on, 'Job')).toEqual(['Cluster'])
  })
})

describe('kindNote', () => {
  it('names the button for a workload kind that owns no pod', () => {
    expect(kindNote('CronJob')).toBe('No pod has the owner kind CronJob. Select Job and CronJob pods.')
    expect(kindNote('Deployment')).toBe(
      'No pod has the owner kind Deployment. Select Deployment pods.',
    )
  })

  it('names the button for a known kind typed with a different case', () => {
    expect(kindNote('job')).toBe('No pod has the owner kind job. Select Job and CronJob pods.')
    expect(kindNote('replicaset')).toBe(
      'No pod has the owner kind replicaset. Select Deployment pods.',
    )
    expect(kindNote('cronjob')).toBe('No pod has the owner kind cronjob. Select Job and CronJob pods.')
  })

  it('gives no note for a kind that can own a pod', () => {
    expect(kindNote('Cluster')).toBeNull()
    expect(kindNote('Job')).toBeNull()
    expect(kindNote('VirtualMachineInstance')).toBeNull()
  })
})

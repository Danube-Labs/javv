/**
 * The owner-kind buttons of the scan scope (issue 891). The scanner compares each listed kind,
 * exactly and with case, to the kind of the pod's DIRECT owner. A Deployment's pods are owned by a
 * ReplicaSet and a CronJob's by a Job, so each button saves the owner kind and is labelled with the
 * workload a user knows. The saved list stays one `ignore_kinds` list: other owner kinds (an
 * operator's own, e.g. CloudNativePG `Cluster`) are typed in the list beside the buttons.
 */
import { addChip, removeChip } from './scopeForm'

export interface KindButton {
  kind: string
  label: string
}

export const KIND_BUTTONS: readonly KindButton[] = [
  { kind: 'ReplicaSet', label: 'Deployment pods' },
  { kind: 'DaemonSet', label: 'DaemonSet pods' },
  { kind: 'StatefulSet', label: 'StatefulSet pods' },
  { kind: 'Job', label: 'Job and CronJob pods' },
]

const BUTTON_KINDS = new Set(KIND_BUTTONS.map((b) => b.kind))

// lowercased value that owns no pod -> the button that skips the pods the user meant
const NO_POD_KINDS = new Map<string, string>([
  ...KIND_BUTTONS.map((b) => [b.kind.toLowerCase(), b.label] as const),
  ['deployment', 'Deployment pods'],
  ['cronjob', 'Job and CronJob pods'],
])

export function splitKinds(kinds: readonly string[]): { selected: Set<string>; typed: string[] } {
  return {
    selected: new Set(kinds.filter((k) => BUTTON_KINDS.has(k))),
    typed: kinds.filter((k) => !BUTTON_KINDS.has(k)),
  }
}

export function toggleKind(kinds: string[], kind: string): string[] {
  return kinds.includes(kind) ? removeChip(kinds, kind) : addChip(kinds, kind)
}

/** The note for a typed value that matches no pod, or null when the value can own a pod. */
export function kindNote(value: string): string | null {
  if (BUTTON_KINDS.has(value)) return null
  const label = NO_POD_KINDS.get(value.toLowerCase())
  return label ? `No pod has the owner kind ${value}. Select ${label}.` : null
}

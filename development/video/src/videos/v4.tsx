// Video 4: change many findings at once.
import shots from '../../public/v4/shots.json'
import type { Video } from '../engine'

const TYPED = Array.from({ length: 8 }, (_, i) => `type-${i + 1}`)

export const v4: Video = {
  dir: 'v4',
  shots,
  title: 'Change many findings at once',
  kicker: 'Triage · video 4 of 6',
  next: 'Next: when a scanner stops sending results',
  steps: 4,
  beats: [
    { shot: 'findings', step: 1, caption: 'Bulk triage changes many findings at once. First, filter the findings.', spot: 'sevFacet' },
    { shot: 'findings', step: 1, caption: 'Select Low in the Severity filter.', spot: 'low', click: { box: 'low', to: 'low' } },
    { shot: 'low', step: 1, caption: 'The count shows how many findings match the filter.', spot: 'head' },
    { shot: 'low', step: 2, caption: 'Select Bulk triage.', spot: 'bulkBtn', click: { box: 'bulkBtn', to: 'bulk', page: true } },
    { shot: 'bulk', step: 2, caption: 'The dialog shows your filters and the number of findings that will change.', spot: 'filters', hold: 'dialog' },
    { shot: 'bulk', step: 2, caption: 'Select the new state. Here, Acknowledge.', spot: 'states', hold: 'dialog', click: { box: 'ack', to: 'bulk-ack' } },
    { shot: 'bulk-ack', step: 2, caption: 'Write a note. JAVV adds the note to each finding.', spot: 'notes', hold: 'dialog', click: { box: 'notes', via: TYPED, to: 'type-9' } },
    { shot: 'type-9', step: 3, caption: 'Select Apply to matching findings.', spot: 'apply', hold: 'dialog', click: { box: 'apply', to: 'done' } },
    { shot: 'done', step: 3, caption: 'JAVV changed all the matching findings. The Audit log records one entry for the change.', spot: 'done', hold: 'dialog', click: { box: 'close', to: 'after', page: true } },
    { shot: 'after', step: 3, caption: 'The State filter now counts the acknowledged findings.', spot: 'stateFacet' },
    { shot: 'after', step: 4, caption: 'Some filters block bulk triage. Here, select Trivy in the Scanner filter.', spot: 'scanFacet', click: { box: 'trivy', to: 'trivy' } },
    { shot: 'trivy', step: 4, caption: 'Select Bulk triage again.', spot: 'bulkBtn', click: { box: 'bulkBtn', to: 'blocked', page: true } },
    { shot: 'blocked', step: 4, caption: 'Bulk triage follows only Severity, State and Assignee. Other filters block it, so it never changes more findings than you see.', spot: 'blocked', hold: 'dialog' },
  ],
}

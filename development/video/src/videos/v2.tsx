// Video 2: set the state of a finding.
import shots from '../../public/v2/shots.json'
import type { Video } from '../engine'

export const v2: Video = {
  dir: 'v2',
  shots,
  title: 'Set the state of a finding',
  kicker: 'Triage · video 2 of 6',
  next: 'Next: accept a risk, with an expiry date',
  steps: 5,
  beats: [
    { shot: 'findings', step: 1, caption: 'Open a finding from the Findings table.', spot: 'row', click: { box: 'row', to: 'finding', page: true } },
    { shot: 'finding', step: 2, caption: 'The triage panel sets the state of this one finding.', spot: 'panel', hold: 'panel' },
    { shot: 'finding', step: 2, caption: 'Select Not affected. Not affected needs a reason.', spot: 'na', hold: 'panel', click: { box: 'na', to: 'not-affected' } },
    { shot: 'not-affected', step: 3, caption: 'Select one of the five standard reasons.', spot: 'reasons', hold: 'panel', click: { box: 'firstReason', to: 'reason' } },
    { shot: 'reason', step: 4, caption: 'Save to audit trail saves the state.', spot: 'save', hold: 'panel', click: { box: 'save', to: 'saved' } },
    { shot: 'saved', step: 4, caption: 'The state changes immediately.', spot: 'state', hold: 'panel' },
    { shot: 'saved', step: 4, caption: 'Only this finding changed. The finding of the other scanner stays Open.', spot: 'evidenceState' },
    { shot: 'saved', step: 5, caption: 'The Activity card of the finding shows who changed the state and when.', spot: 'activity', hold: 'panel' },
    { shot: 'saved', step: 5, caption: 'The Audit log shows all the triage changes. Open it from the side menu.', spot: 'auditLink', click: { box: 'auditLink', to: 'audit', page: true } },
    { shot: 'audit', step: 5, caption: 'The new entry is at the top: when, who, and what changed.', spot: 'top' },
  ],
}

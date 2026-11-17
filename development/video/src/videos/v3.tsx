// Video 3: accept a risk, with an expiry date.
import shots from '../../public/v3/shots.json'
import type { Video } from '../engine'

const TYPED = Array.from({ length: 9 }, (_, i) => `type-${i + 1}`)

export const v3: Video = {
  dir: 'v3',
  shots,
  title: 'Accept a risk, with an expiry date',
  kicker: 'Triage · video 3 of 6',
  next: 'Next: change many findings at once',
  steps: 4,
  beats: [
    { shot: 'findings', step: 1, caption: 'Open a finding from the Findings table.', spot: 'row', click: { box: 'row', to: 'finding', page: true } },
    { shot: 'finding', step: 1, caption: 'A risk acceptance applies to one vulnerability in a scope. Select Note and more.', spot: 'more', hold: 'panel', click: { box: 'more', to: 'more' } },
    { shot: 'more', step: 1, caption: 'Select Accept the risk of this vulnerability.', spot: 'accept', hold: 'panel', click: { box: 'accept', to: 'dialog', page: true } },
    { shot: 'dialog', step: 2, caption: 'Select a namespace. The acceptance covers this vulnerability in that namespace.', spot: 'nsField', hold: 'dialog', click: { box: 'nsOption', to: 'dialog-ns' } },
    { shot: 'dialog-ns', step: 2, caption: 'This line shows the scope. The acceptance also covers new findings in the namespace.', spot: 'blast', hold: 'dialog' },
    { shot: 'dialog-ns', step: 3, caption: 'Set an expiry date. When this date passes, the findings become Open again.', spot: 'expiry', hold: 'dialog', click: { box: 'expiry', to: 'dialog-expiry' } },
    { shot: 'dialog-expiry', step: 3, caption: 'Write the reason. Other users read it on the Approval list.', spot: 'reason', hold: 'dialog', click: { box: 'reason', via: TYPED, to: 'type-10' } },
    { shot: 'type-10', step: 3, caption: 'Select Create decision.', spot: 'create', hold: 'dialog', click: { box: 'create', to: 'accepted', page: true } },
    { shot: 'accepted', step: 4, caption: 'The risk acceptance is in effect. It shows in Decisions on this vulnerability.', spot: 'decisionRow' },
    { shot: 'accepted', step: 4, caption: 'The Approval list shows all risk acceptances in effect. Open it from the side menu.', spot: 'approvalsLink', click: { box: 'approvalsLink', to: 'approvals', page: true } },
    { shot: 'approvals', step: 4, caption: 'Each row shows the vulnerability, the scope, the reason and the expiry date.', spot: 'first', wide: true },
    { shot: 'approvals', step: 4, caption: 'To stop a risk acceptance, select Revoke.', spot: 'revoke', click: { box: 'revoke', to: 'armed' } },
    { shot: 'armed', step: 4, caption: 'Select Confirm revoke.', spot: 'confirm', click: { box: 'confirm', to: 'revoked' } },
    { shot: 'revoked', step: 4, caption: 'The risk acceptance stops. Its findings become Open again.', spot: 'empty', wide: true },
  ],
}

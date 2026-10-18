// Video 6: see who changed what.
import shots from '../../public/v6/shots.json'
import type { Video } from '../engine'

export const v6: Video = {
  dir: 'v6',
  shots,
  title: 'See who changed what',
  kicker: 'Triage · video 6 of 6',
  next: 'More help: the Guide, in the side menu',
  steps: 3,
  beats: [
    { shot: 'audit', step: 1, caption: 'The Audit log lists each change: when, who, what and the target.', spot: 'table', wide: true },
    { shot: 'audit', step: 2, caption: 'Filter by user to see the changes of one person.', spot: 'userFacet', click: { box: 'lead', to: 'lead' } },
    { shot: 'lead', step: 2, caption: 'Filter by action. Here, Bulk triage.', spot: 'actionFacet', click: { box: 'bulk', to: 'bulk' } },
    { shot: 'bulk', step: 2, caption: 'One bulk change is one entry in the Audit log.', spot: 'first', wide: true },
    { shot: 'bulk', step: 3, caption: 'Export CSV saves the entries as a file.', spot: 'exportBtn' },
    { shot: 'bulk', step: 3, caption: 'A finding also has its own history. Open Findings.', spot: 'findingsLink', click: { box: 'findingsLink', to: 'findings', page: true } },
    { shot: 'findings', step: 3, caption: 'Select Not affected in the State filter.', spot: 'stateFacet', click: { box: 'ackFilter', to: 'acked' } },
    { shot: 'acked', step: 3, caption: 'Open the finding.', spot: 'row', wide: true, click: { box: 'row', to: 'finding', page: true } },
    { shot: 'finding', step: 3, caption: 'The Activity card shows the changes that a person made on this one finding, with who and when.', spot: 'activity', hold: 'panel' },
  ],
}

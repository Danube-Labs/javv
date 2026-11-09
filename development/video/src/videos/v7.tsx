// Video 7: build a dashboard.
import shots from '../../public/v7/shots.json'
import type { Video } from '../engine'

const DRAG = Array.from({ length: 6 }, (_, i) => `drag-${i + 1}`)

export const v7: Video = {
  dir: 'v7',
  shots,
  title: 'Build a dashboard',
  kicker: 'Dashboards',
  next: 'More help: the Guide, in the side menu',
  steps: 11,
  beats: [
    // 1. make
    { shot: 'list', step: 1, caption: 'A dashboard puts panels of Overview, Contributors and Scanner status on one page. Open Dashboards from the side menu.', spot: 'nav' },
    { shot: 'list', step: 1, caption: 'Select New dashboard.', spot: 'create', click: { box: 'create', to: 'details', page: true } },
    { shot: 'details', step: 1, caption: 'Type a name. The description is optional.', spot: 'name', hold: 'dialog', click: { box: 'name', via: ['type-1', 'type-2'], to: 'named' } },
    { shot: 'named', step: 1, caption: 'Select who can see the dashboard. Here, Some roles.', spot: 'someRoles', hold: 'dialog', click: { box: 'someRoles', to: 'roles' } },
    { shot: 'roles', step: 1, caption: 'Select one role or more. Here, viewer.', spot: 'roles', hold: 'dialog', click: { box: 'viewer', to: 'roles-on' } },
    { shot: 'roles-on', step: 1, caption: 'Opens on sets the scanner that the dashboard opens with.', spot: 'opensOn', hold: 'dialog' },
    { shot: 'roles-on', step: 1, caption: 'Select Create. The dashboard opens in edit mode, with no panels.', spot: 'createBtn', hold: 'dialog', click: { box: 'createBtn', to: 'empty', page: true } },
    // 2. add
    { shot: 'empty', step: 2, caption: 'Select Add panel.', spot: 'addPanel', click: { box: 'addPanel', to: 'catalog', page: true } },
    { shot: 'catalog', step: 2, caption: 'The catalog shows the panels in groups. Select a panel.', spot: 'list', hold: 'cat', click: { box: 'row', to: 'p1-picked' } },
    { shot: 'p1-picked', step: 2, caption: 'The preview shows the panel with the data of the selected cluster.', spot: 'preview', hold: 'cat' },
    { shot: 'p1-picked', step: 2, caption: 'Set the width. Some panels also have a height or a scanner to set. Then select Add panel.', spot: 'opts', hold: 'cat', click: { box: 'add', to: 'p1-added', page: true } },
    { shot: 'p1-added', step: 2, caption: 'Add two more panels.', spot: 'addPanel', click: { box: 'addPanel', to: 'p2-picked', page: true } },
    { shot: 'p2-picked', step: 2, caption: 'Here, Findings by namespace. Select Add panel.', spot: 'add', hold: 'cat', click: { box: 'add', to: 'p2-added', page: true } },
    { shot: 'p2-added', step: 2, caption: 'Each new panel goes under the other panels.', spot: 'added' },
    { shot: 'p2-added', step: 2, caption: 'Select Add panel again.', spot: 'addPanel', click: { box: 'addPanel', to: 'p3-picked', page: true } },
    { shot: 'p3-picked', step: 2, caption: 'Then Top components.', spot: 'add', hold: 'cat', click: { box: 'add', to: 'p3-added', page: true } },
    // 3. move
    { shot: 'before-drag', step: 3, caption: 'To move a panel, drag its Move tab.', spot: 'move', click: { box: 'move', via: DRAG, to: 'dropped', drag: 'moved' } },
    { shot: 'dropped', step: 3, caption: 'The dashed box showed where the panel goes. The panel is now at the right.', spot: 'moved' },
    // 4. change
    { shot: 'settings-btn', step: 4, caption: 'To change a panel, select Settings on it.', spot: 'settings', click: { box: 'settings', to: 'settings' } },
    { shot: 'settings', step: 4, caption: 'Set the height. Tall shows more rows.', spot: 'tall', hold: 'pop', click: { box: 'tall', to: 'settings-tall' } },
    { shot: 'settings-tall', step: 4, caption: 'Select a scanner to pin the panel to it. A pinned panel does not follow the dashboard scanner.', spot: 'scanner', hold: 'pop', click: { box: 'trivy', to: 'nsf-bar' } },
    { shot: 'nsf-bar', step: 4, caption: 'In Filters, select Add filter.', spot: 'add', hold: 'pop', click: { box: 'add', to: 'nsf-fields' } },
    { shot: 'nsf-fields', step: 4, caption: 'Select a field. Here, Severity.', spot: 'menu', hold: 'pop', click: { box: 'field', to: 'nsf-values' } },
    { shot: 'nsf-values', step: 4, caption: 'Select one value or more. Here, high.', spot: 'value', hold: 'pop', click: { box: 'value', to: 'settings-set' } },
    { shot: 'settings-set', step: 4, caption: 'Select Apply.', spot: 'apply', hold: 'pop', click: { box: 'apply', to: 'applied' } },
    { shot: 'applied', step: 4, caption: 'The panel is taller. It shows the pinned scanner, and a filter button over its corner.', spot: 'panel', click: { box: 'filterBtn', to: 'filter-list' } },
    { shot: 'filter-list', step: 4, caption: 'The list shows the filters of the panel. Open in Findings shows the same findings.', spot: 'pop' },
    // 5. triage activity
    { shot: 'triage-start', step: 5, caption: 'Add the Triage activity panel. It shows the triage changes that people made.', spot: 'addPanel', click: { box: 'addPanel', to: 'ta-picked', page: true } },
    { shot: 'ta-picked', step: 5, caption: 'Select Add panel.', spot: 'add', hold: 'cat', click: { box: 'add', to: 'ta-added', page: true } },
    { shot: 'ta-added', step: 5, caption: 'The panel goes under the other panels.', spot: 'added' },
    { shot: 'ta-settings-btn', step: 5, caption: 'Select Settings. The filters of Triage activity are Action and User.', spot: 'settings', click: { box: 'settings', to: 'taf-bar' } },
    { shot: 'taf-bar', step: 5, caption: 'Select Add filter.', spot: 'add', hold: 'pop', click: { box: 'add', to: 'taf-fields' } },
    { shot: 'taf-fields', step: 5, caption: 'Select User.', spot: 'menu', hold: 'pop', click: { box: 'field', to: 'taf-values' } },
    { shot: 'taf-values', step: 5, caption: 'Select a user. Here, lead.', spot: 'value', hold: 'pop', click: { box: 'value', to: 'ta-set' } },
    { shot: 'ta-set', step: 5, caption: 'Select Apply. The panel counts only the changes of lead.', spot: 'apply', hold: 'pop', click: { box: 'apply', to: 'before-remove' } },
    // 6. delete a panel
    { shot: 'before-remove', step: 6, caption: 'To delete a panel, select the bin icon on it.', spot: 'remove', click: { box: 'remove', to: 'removed' } },
    // 7. save
    { shot: 'removed', step: 7, caption: 'Discard puts back the dashboard as it was at the last save. Select Save changes.', spot: 'bar', click: { box: 'save', to: 'saved' } },
    { shot: 'saved', step: 7, caption: 'Name and sharing changes the name, the description and who can see the dashboard.', spot: 'details', click: { box: 'details', to: 'details-edit', page: true } },
    { shot: 'details-edit', step: 7, caption: 'It has the same fields as New dashboard.', spot: 'dialog', hold: 'dialog' },
    { shot: 'exit', step: 7, caption: 'Select Exit edit.', spot: 'exit', click: { box: 'exit', to: 'read', page: true } },
    // 8. read
    { shot: 'read', step: 8, caption: 'This is the page that the users see. The scanner switch changes the scanner of each panel.', spot: 'switch', click: { box: 'grype', to: 'read-grype' } },
    { shot: 'read-grype', step: 8, caption: 'The other panels show grype now. The pinned panel keeps trivy.', spot: 'pinned' },
    { shot: 'read-all', step: 8, caption: 'Select the filter button of a panel.', spot: 'filterBtn', click: { box: 'filterBtn', to: 'read-filters' } },
    { shot: 'read-filters', step: 8, caption: 'Select Open in Findings.', spot: 'open', hold: 'pop', click: { box: 'open', to: 'findings', page: true } },
    { shot: 'findings', step: 8, caption: 'The Findings page shows the same findings, with the same filters.', spot: 'bar', wide: true },
    { shot: 'read-back', step: 8, caption: 'On Triage activity, the filter button opens the Audit log.', spot: 'filterBtn', click: { box: 'filterBtn', to: 'ta-filters' } },
    { shot: 'ta-filters', step: 8, caption: 'Select Open in Audit log.', spot: 'open', hold: 'pop', click: { box: 'open', to: 'audit', page: true } },
    { shot: 'audit', step: 8, caption: 'The Audit log shows the changes with the same filters.', spot: 'bar', wide: true },
    // 9. copy
    { shot: 'read-export', step: 9, caption: 'Export saves the dashboard as a file.', spot: 'exportBtn', click: { box: 'exportBtn', to: 'list-one', page: true } },
    { shot: 'list-one', step: 9, caption: 'On the Dashboards page, Export all saves all the dashboards that you can see. Select Import.', spot: 'importBtn', click: { box: 'importBtn', to: 'import', page: true } },
    { shot: 'import', step: 9, caption: 'Select the file.', spot: 'choose', hold: 'dialog', click: { box: 'choose', to: 'import-file' } },
    { shot: 'import-file', step: 9, caption: 'Keep the IDs makes the same dashboards on a different JAVV. Make copies gives each one a new ID.', spot: 'ids', hold: 'dialog', click: { box: 'copies', to: 'import-copy' } },
    { shot: 'import-copy', step: 9, caption: 'Select Import.', spot: 'run', hold: 'dialog', click: { box: 'run', to: 'imported' } },
    { shot: 'imported', step: 9, caption: 'The result shows each line of the file. You are the owner of each dashboard that the import makes.', spot: 'dialog', hold: 'dialog', click: { box: 'done', to: 'list-two', page: true } },
    // 10. delete
    { shot: 'list-two', step: 10, caption: 'Open the copy to delete it.', spot: 'copy', click: { box: 'copy', to: 'copy', page: true } },
    { shot: 'copy', step: 10, caption: 'Select Edit dashboard.', spot: 'edit', click: { box: 'edit', to: 'copy-edit', page: true } },
    { shot: 'copy-edit', step: 10, caption: 'Select Delete.', spot: 'remove', click: { box: 'remove', to: 'remove', page: true } },
    { shot: 'remove', step: 10, caption: 'Select Delete dashboard. The data of the panels stays. The audit log keeps a copy of the dashboard.', spot: 'dialog', hold: 'dialog', click: { box: 'confirm', to: 'list-after', page: true } },
    { shot: 'list-after', step: 10, caption: 'The first dashboard stays.', spot: 'card' },
    // 11. a viewer
    { shot: 'viewer', step: 11, caption: 'A user with the viewer role sees the dashboard. Edit dashboard is off, and the reason shows next to it.', spot: 'note', wide: true },
  ],
}

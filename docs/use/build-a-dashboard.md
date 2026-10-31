# Build a dashboard

A dashboard puts panels of Overview, Contributors and Scanner status on one page. Each panel
shows the data of the cluster that you select at the top of the page.

## Prerequisites

- A role that allows dashboards: `triager`, `security_lead` or `admin`
  ([What your role lets you do](index.md#what-your-role-lets-you-do)).

## Make a dashboard

1. Open Dashboards from the side menu.
2. Select New dashboard.
3. Type a name. The description is optional.
4. Select who can see the dashboard: Only me, Everyone or Some roles. With Some roles, select one
   role or more.
5. Select the scanner that the dashboard opens with.
6. Select Create. The dashboard opens in edit mode, with no panels.

## Add and move panels

1. Select Add panel. The catalog shows the panels in groups.
2. Select a panel. The preview shows the panel with the data of the selected cluster.
3. Set the width of the panel. Some panels also have a height or a scanner to set.
4. Select Add panel. The panel goes under the other panels.
5. To move a panel, drag its Move tab with the mouse. A dashed box shows where the panel goes.
   You cannot move a panel with the keyboard.
6. To change a panel, select Settings on the panel. To remove a panel, select the bin icon on it.
7. Select Save changes. Discard puts back the dashboard as it was at the last save.

A dashboard has at most 24 panels.

## Filter a panel

Five panels can count only some findings: Findings summary, Package type, Findings by namespace,
Top components and Triage progress.

1. Open the dashboard, then select Edit dashboard.
2. On the panel, select Settings.
3. In Filters, select Add filter. Select a field, then select or type one value or more. To leave
   out the values, select is not.
4. Select Apply, then select Save changes.

A panel with filters shows 1 filter or a number of filters over its top right corner. Select it to
see the filters. Open in Findings shows the same findings on the Findings page.

- The list has no Scanner filter. Use the Scanner setting of the panel.
- Triage progress shows each state, so its list has no State filter.
- New in range counts the findings first seen in the time range at the top of the page.

To remove the filters of a panel, select Clear all in Filters. Then select Apply and Save changes.

## Change the name or the sharing

1. Open the dashboard, then select Edit dashboard.
2. Select Name and sharing. Change the fields, then select Apply.
3. Select Save changes.

Only the owner of a dashboard and an admin can change it. An admin can see each dashboard.

## Remove a dashboard

1. Open the dashboard, then select Edit dashboard.
2. Select Remove, then select Remove dashboard. The data of the panels stays. The audit log keeps
   a copy of the dashboard.

## Copy dashboards to a different JAVV

1. On the Dashboards page, select Export all. On the page of one dashboard, select Export.
2. On the other JAVV, open Dashboards and select Import. Select the file.
3. Select Keep the IDs, or Make copies. You are the owner of each dashboard that the import
   makes.

If a dashboard in the file names a role that the other JAVV does not have, the import
does not make that dashboard. The result of the import shows the line.

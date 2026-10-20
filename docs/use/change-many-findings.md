# Change many findings at once

<video controls preload="metadata" width="100%" src="videos/change-many-findings.mp4"></video>

Bulk triage changes many findings at once. First, filter the findings.

## Prerequisites

- A role that allows triage: `triager`, `security_lead` or `admin`
  ([What your role lets you do](index.md#what-your-role-lets-you-do)).

## Steps

1. Select a value in a filter, for example Low in the Severity filter. The count shows how many
   findings match the filter.
2. Select Bulk triage. The dialog shows your filters and the number of findings that will change.
3. Select the new state, for example Acknowledge.
4. Write a note. JAVV adds the note to each finding.
5. Select Apply to matching findings. JAVV changes all the matching findings. The Audit log
   records one entry for the change.
6. The State filter now counts the changed findings.

## Filters that block bulk triage

Bulk triage follows only the Severity, State and Assignee filters. Other filters, for example the
Scanner filter, block it. Thus bulk triage never changes more findings than you see.

Next: [When a scanner stops sending results](when-a-scanner-stops.md).

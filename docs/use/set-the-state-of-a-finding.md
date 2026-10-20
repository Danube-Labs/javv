# Set the state of a finding

<video controls preload="metadata" width="100%" src="videos/set-the-state-of-a-finding.mp4"></video>

## Prerequisites

- A role that allows triage: `triager`, `security_lead` or `admin`
  ([What your role lets you do](index.md#what-your-role-lets-you-do)).

## Steps

1. Open a finding from the Findings table. The triage panel sets the state of this one finding.
2. Select Not affected. Not affected needs a reason: select one of the five standard reasons.
3. Select Save to audit trail. The state changes immediately.
4. Only this finding changes. The finding of the other scanner stays Open.
5. The Activity card of the finding shows who changed the state and when.
6. To see all the triage changes, open the Audit log from the side menu. The new entry is at the
   top: when, who, and what changed.

Next: [Accept a risk, with an expiry date](accept-a-risk.md).

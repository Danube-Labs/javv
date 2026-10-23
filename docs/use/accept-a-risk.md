# Accept a risk, with an expiry date

<video controls preload="metadata" width="100%" src="videos/accept-a-risk.mp4"></video>

A risk acceptance applies to one CVE in a scope. It also covers the new findings of that CVE in
the scope.

## Prerequisites

- A role that allows risk acceptance: `security_lead` or `admin`
  ([What your role lets you do](index.md#what-your-role-lets-you-do)).

## Steps

1. Open a finding from the Findings table.
2. Select Risk-accept this CVE.
3. Select a namespace. The acceptance covers this CVE in that namespace. A line in the dialog
   shows the scope.
4. Set an expiry date. The first date that you can select is tomorrow in UTC. When this date
   passes, the findings become Open again.
5. Write the reason. Other users read it on the Approval list.
6. Select Create decision. The risk acceptance is in effect. It shows in Decisions on this CVE.
7. The Approval list shows all the risk acceptances in effect. Open it from the side menu. Each
   row shows the CVE, the scope, the reason and the expiry date.

## Stop a risk acceptance

1. On the Approval list, select Revoke.
2. Select Confirm revoke. The risk acceptance stops, and its findings become Open again.

Next: [Change many findings at once](change-many-findings.md).

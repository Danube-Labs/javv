# Use JAVV

These pages show how to triage the findings in JAVV, from the first scan to a finding with a
decision. Each page has a short video. The same steps are in text below each video.

| Video | What it shows |
|---|---|
| [From a scan to a finding](from-a-scan-to-a-finding.md) | How the results of the two scanners get to JAVV, and how to find one finding |
| [Set the state of a finding](set-the-state-of-a-finding.md) | How to set the state of one finding, and where JAVV records the change |
| [Accept a risk, with an expiry date](accept-a-risk.md) | How to accept the risk of one CVE in a scope, and how to stop it |
| [Change many findings at once](change-many-findings.md) | How to change the state of all the findings that match your filters |
| [When a scanner stops sending results](when-a-scanner-stops.md) | What JAVV does when a scanner is silent for too long |
| [See who changed what](who-changed-what.md) | How to find the changes in the Audit log and on a finding |

The videos use made-up clusters and data.

## What your role lets you do

Your role sets what you can change:

- To set the state of a finding, or of many findings at once, your role must allow triage. The
  `triager`, `security_lead` and `admin` roles allow it.
- To accept a risk, or to revoke a risk acceptance, your role must allow risk acceptance. The
  `security_lead` and `admin` roles allow it.
- To download a file of the data, for example a CSV or VEX file, your role must allow export. The
  `triager`, `security_lead` and `admin` roles allow it. The `viewer` role does not. For a viewer,
  each export button is not available, and the text next to it tells you why.

An administrator sets the role of each user.

## More help

The Guide in the side menu of JAVV explains the states, the reasons and the risk acceptances.

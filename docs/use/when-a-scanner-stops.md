# When a scanner stops sending results

<video controls preload="metadata" width="100%" src="videos/when-a-scanner-stops.mp4"></video>

The video is 1 minute long and has no sound.
[Download the video](videos/when-a-scanner-stops.mp4).

## What JAVV does

Each scan refreshes the findings that the scanner sees. If a scanner sends no results for too
long, JAVV marks its findings Stale. JAVV keeps the old state. When a scan sees the finding again,
JAVV restores the old state.

## Steps

1. A banner on Findings shows that a scanner is silent. The data of the cluster can be old.
2. The State filter counts the Stale findings.
3. Open Scanner status from the side menu. It shows when each scanner sent its last results.
4. Go back to Findings and open a Stale finding. A note shows that JAVV set this state, because
   the scanner is silent. A state that a person sets replaces it.

Next: [See who changed what](who-changed-what.md).

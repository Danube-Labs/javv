<script setup lang="ts">
import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'

import GuideProse from './GuideProse.vue'
</script>

<template>
  <GuideProse>
    <p>
      JAVV runs two scanners, <ScannerTag name="trivy" /> and <ScannerTag name="grype" />, and keeps
      their results apart. Every finding belongs to one scanner, and counts are shown per scanner, side
      by side. <span class="ui-name">All scanners</span> shows Trivy and Grype together: a CVE that both
      report counts once for each. JAVV never averages or merges their results.
    </p>
    <p>
      The two often differ, because each uses its own vulnerability data. One may report a CVE the other
      doesn't, or rate it differently. When both report the same CVE in the same package of an image with
      different severities, the finding is marked <DisagreementBadge />. JAVV shows the disagreement; it
      doesn't decide who is right.
    </p>
    <p>Some details come from one scanner only: KEV and EPSS are reported by Grype.</p>
    <p class="count-unit">
      JAVV counts findings. A finding is one CVE in one package version, in one image, from one
      scanner. A scanner report can show the same finding more than one time: one time for each file
      that holds the package. For example, the Trivy report for rancher/local-path-provisioner v0.0.36
      has 371 entries. JAVV shows 101 findings for this image. The Go standard library is in 11
      programs of the image, thus Trivy shows each of its CVEs 11 times.
    </p>
  </GuideProse>
</template>

<script setup lang="ts">
/** The bulk limit is the default of `JAVV_BULK_INLINE_LIMIT` of docs/CONFIGURATION.md: the backend
 * can have another value, so the text says "by default". */
import StateTag from '@/components/chips/StateTag.vue'
import { CISA_JUSTIFICATIONS, PANEL_TARGETS } from '@/findings/triageRules'

import GuideProse from './GuideProse.vue'

const PERSON_STATES = PANEL_TARGETS.map((t) => t.state)
</script>

<template>
  <GuideProse>
    <p>Every finding has one of six states.</p>
    <ul>
      <li>
        <strong>Set from a finding:</strong>
        <span class="state-row"><StateTag v-for="s in PERSON_STATES" :key="s" :state="s" /></span>
      </li>
      <li>
        <strong>Set by a risk acceptance:</strong> <StateTag state="risk_accepted" />. You accept a vulnerability for
        a scope (some namespaces or images, or the whole cluster) with an optional expiry date. A namespace
        scope or a cluster scope also covers the matching findings that appear later. An image scope does not.
      </li>
      <li>
        <strong>Set only by JAVV:</strong> <StateTag state="stale" />, when it can no longer confirm the
        finding (see Scans and freshness).
      </li>
    </ul>
    <p>
      <strong>Not affected needs a reason,</strong> one of five standard ones (VEX). JAVV has no separate
      “false positive” state. Use Not affected with one of the first two reasons.
    </p>
    <ul class="reasons">
      <li v-for="j in CISA_JUSTIFICATIONS" :key="j.id">{{ j.label }} <span class="maps">· {{ j.maps }}</span></li>
    </ul>
    <p>
      <strong>You cannot change a risk acceptance.</strong> To change its scope or its expiry date, revoke
      it and create a new one. The revoked one stays in the list with a line through it, so JAVV keeps its
      history.
    </p>
    <p>
      <strong>A bulk change applies only to the findings that the filters select.</strong> Some filters
      cannot go into a bulk change, for example a scanner, KEV, namespace or image filter. With such a
      filter, JAVV stops the bulk change, so that it does not change more rows than you see. If a bulk
      change selects more findings than the bulk limit (5,000 by default), JAVV refuses it. Add filters
      first.
    </p>
  </GuideProse>
</template>

<style scoped>
.state-row {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  vertical-align: middle;
}
.reasons {
  list-style: none;
  padding-left: 0;
  gap: var(--space-1);
}
.maps {
  color: var(--soft);
}
</style>

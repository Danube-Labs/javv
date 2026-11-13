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
        <strong>Set by a risk acceptance:</strong> <StateTag state="risk_accepted" />. You accept a CVE for
        a scope (some namespaces or images, or the whole cluster) with an optional expiry. A namespace or
        cluster scope also covers matching findings that appear later; an image scope doesn't.
      </li>
      <li>
        <strong>Set only by JAVV:</strong> <StateTag state="stale" />, when it can no longer confirm the
        finding (see Scans and freshness).
      </li>
    </ul>
    <p>
      <strong>Not affected needs a reason,</strong> one of five standard ones (VEX). There is no separate
      “false positive” state: it's Not affected with one of the first two reasons.
    </p>
    <ul class="reasons">
      <li v-for="j in CISA_JUSTIFICATIONS" :key="j.id">{{ j.label }} <span class="maps">· {{ j.maps }}</span></li>
    </ul>
    <p>
      <strong>A risk acceptance can't be edited.</strong> To change its scope or expiry, revoke it and
      create a new one. The revoked one stays listed, struck through, so its history is kept.
    </p>
    <p>
      <strong>Bulk changes apply to exactly what the filters describe.</strong> If a filter can't be
      expressed in a bulk change (a scanner, KEV, namespace or image filter, for example), bulk is
      blocked rather than changing more rows than you see. A bulk change matching more findings than the
      bulk limit (5,000 by default) is refused; narrow the filters first.
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

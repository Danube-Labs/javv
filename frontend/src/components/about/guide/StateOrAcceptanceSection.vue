<script setup lang="ts">
/** Written in Simplified Technical English (issue 698): short sentences, one name per thing.
 * "state", "risk acceptance" and "Approval list" are those names; keep them when you edit. */
import StateTag from '@/components/chips/StateTag.vue'
import { CISA_JUSTIFICATIONS, PANEL_TARGETS } from '@/findings/triageRules'

import GuideProse from './GuideProse.vue'

const PERSON_STATES = PANEL_TARGETS.map((t) => t.state)
const FIRST_REASON = CISA_JUSTIFICATIONS[0].label
</script>

<template>
  <GuideProse>
    <p>
      You can handle a finding in two ways. You can set a state on one finding. You can accept the risk of
      one CVE for a scope.
    </p>

    <p><strong>Set a state</strong></p>
    <ul>
      <li>
        A state applies to one finding. A finding is one CVE in one package of one image, from one scanner.
      </li>
      <li>
        You set the state in the triage panel of the finding:
        <span class="state-row"><StateTag v-for="s in PERSON_STATES" :key="s" :state="s" /></span>
      </li>
      <li>To set a state, your role must allow triage.</li>
      <li>
        A state has no scope and no expiry date. JAVV does not change it, with one exception: JAVV sets
        <StateTag state="stale" /> when the scanner sends scans but no scan saw the finding during the
        freshness window. JAVV also sets Stale when the scanner sent no scans during the scanner-down
        window. When a scan sees the finding again, or reports it gone, the next staleness sweep restores
        the state that the finding had before Stale. A risk acceptance made in the meantime still applies.
      </li>
    </ul>

    <p><strong>Accept the risk</strong></p>
    <ul>
      <li>
        A risk acceptance applies to one CVE in a scope. The scope is some namespaces, some images, or the
        whole cluster.
      </li>
      <li>
        You create a risk acceptance with the button <span class="ui-name">Risk-accept this CVE</span> on a
        finding. You write a reason. You can set an expiry date.
      </li>
      <li>To create or revoke a risk acceptance, your role must allow risk acceptance.</li>
      <li>
        A risk acceptance sets <StateTag state="risk_accepted" /> on the Open findings in its scope. A finding
        in its scope with a different state keeps that state.
      </li>
      <li>
        When you revoke a risk acceptance, those findings become Open again. After the expiry date, the
        next staleness sweep makes those findings Open again.
      </li>
    </ul>

    <p><strong>The Approval list</strong></p>
    <ul>
      <li>
        The Approval list shows each risk acceptance that is in effect. The earliest expiry date is first.
      </li>
      <li>
        No item on the Approval list waits for approval. A risk acceptance is in effect from the moment you
        save it.
      </li>
      <li>
        Use the Approval list to examine each risk acceptance before its expiry date. Revoke a risk
        acceptance that is no longer necessary.
      </li>
      <li>
        A finding with the state Not affected or Resolved is not on the Approval list. Those are states, not
        risk acceptances.
      </li>
      <li>
        A revoked risk acceptance is not on the Approval list. It stays on the finding, in
        <span class="ui-name">Decisions on this CVE</span>, with a line through it.
      </li>
      <li>To see the Approval list, your role must allow risk acceptance.</li>
    </ul>

    <p><strong>Example 1: the image does not use the vulnerable code</strong></p>
    <ol>
      <li>Open the finding. Its state is Open.</li>
      <li>Set the state to Not affected.</li>
      <li>Select a reason, for example {{ FIRST_REASON }}.</li>
      <li>Save. The Audit log records the change.</li>
    </ol>
    <p>The finding is not on the Approval list, because you set a state.</p>

    <p><strong>Example 2: the image uses the vulnerable code, and no fix is available</strong></p>
    <ol>
      <li>Open the finding. Its state is Open.</li>
      <li>Select <span class="ui-name">Risk-accept this CVE</span>.</li>
      <li>Select the namespace as the scope.</li>
      <li>Write the reason.</li>
      <li>Set an expiry date.</li>
      <li>Save. JAVV sets Risk accepted on each Open finding of this CVE in that namespace.</li>
      <li>The risk acceptance is now on the Approval list.</li>
      <li>Before the expiry date, examine the risk acceptance on the Approval list.</li>
      <li>
        If the risk is still acceptable, revoke the risk acceptance. Then create a new one with a later
        expiry date.
      </li>
      <li>If you do nothing, the risk acceptance expires. The findings become Open again.</li>
    </ol>
  </GuideProse>
</template>

<style scoped>
.state-row {
  display: inline-flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  vertical-align: middle;
}
</style>

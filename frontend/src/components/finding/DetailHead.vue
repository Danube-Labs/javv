<script setup lang="ts">
/**
 * The finding-detail header band (split from FindingDetailView, audit F-15): CVE title row
 * (severity chip, disagreement badge, KEV), the fact strip, and the risk band (CVSS/EPSS/SLA
 * on the stat-card grammar). Header renders only real doc fields (B-2/B-3); the SLA countdown
 * derives FROM the server's due_at (B-5) measured on the D28 display clock — never client math
 * for the deadline itself.
 */
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

import DisagreementBadge from '@/components/chips/DisagreementBadge.vue'
import SevChip from '@/components/chips/SevChip.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { fmtAt, num } from '@/findings/format'
import type { FindingRow } from '@/stores/findings'
import { useTimeTravelStore } from '@/stores/timeTravel'
import { refNowMs } from '@/system/clock'

const props = defineProps<{
  cveId: string
  primary: FindingRow | null
  digest: string | null
  kev: boolean
  disagrees: boolean
  epss: { value: number; scanner: string } | null
}>()

const timeTravel = useTimeTravelStore()

const slaDaysLeft = computed(() => {
  const due = props.primary?.due_at
  if (typeof due !== 'string') return null
  return Math.ceil((new Date(due).getTime() - refNowMs(timeTravel.t)) / 86_400_000)
})
const slaTier = computed(() => {
  if (props.primary?.overdue === true) return 'risk-num-over'
  const d = slaDaysLeft.value
  return d !== null && d <= 3 ? 'risk-num-tight' : ''
})
</script>

<template>
  <div class="detail-head">
    <div class="detail-head-main">
      <div class="detail-cve">
        <h1>{{ cveId }}</h1>
        <SevChip v-if="primary" :level="primary.severity_canonical" />
        <DisagreementBadge v-if="disagrees" label="scanners disagree" title="Scanners disagree on severity" />
        <span v-if="kev" class="kev-lg">KEV · known-exploited</span>
      </div>
      <div class="detail-meta">
        <div class="fact">
          <em>Package</em>
          <span class="fact-val mono-cell">{{ primary?.package_name }}</span>
        </div>
        <div class="fact">
          <em>Image</em>
          <RouterLink
            v-if="digest && primary?.image_repo"
            class="fact-val mono-cell fact-link"
            :to="{
              path: `/images/${digest}`,
              query: { repo: primary.image_repo, ...(primary.tag ? { tag: primary.tag } : {}) },
            }"
            title="Open this image's detail"
            >{{ primary.image_repo }}{{ primary.tag ? ':' + primary.tag : ''
            }}<AppIcon class="fact-go" name="chevron" :size="11"
          /></RouterLink>
          <span v-else class="fact-val mono-cell">{{ primary?.image_repo }}{{ primary?.tag ? ':' + primary.tag : '' }}</span>
        </div>
        <div class="fact">
          <em>First seen</em>
          <span class="fact-val">{{ fmtAt(primary?.first_seen_at) }}</span>
        </div>
        <div class="fact">
          <em>Last seen</em>
          <span class="fact-val">{{ fmtAt(primary?.last_seen_at) }}</span>
        </div>
      </div>
    </div>
    <div class="risk-band">
      <div class="risk-cell">
        <span class="risk-label">CVSS</span>
        <span class="risk-num" :class="`risk-num-${primary?.severity_canonical}`">{{ num(primary?.cvss) }}</span>
        <span class="risk-sub">via {{ primary?.scanner }}</span>
      </div>
      <div class="risk-cell">
        <span class="risk-label">EPSS</span>
        <span class="risk-num"><template v-if="epss">{{ Math.round(epss.value * 100) + '%' }}</template><span v-else class="muted-dash">-</span></span>
        <span class="risk-sub">{{ epss ? `via ${epss.scanner}` : 'not scored' }}</span>
      </div>
      <div class="risk-cell">
        <span class="risk-label">SLA</span>
        <template v-if="primary?.due_at">
          <span class="risk-num" :class="slaTier">{{ slaDaysLeft }}<em>d</em></span>
          <span class="risk-sub">{{ primary.overdue ? 'Overdue' : 'by' }} {{ fmtAt(primary.due_at) }}</span>
        </template>
        <template v-else>
          <span class="risk-num risk-num-quiet">-</span>
          <span class="risk-sub">{{
            ['resolved', 'not_affected', 'risk_accepted'].includes(primary?.state ?? '')
              ? `no deadline · ${primary?.state === 'not_affected' ? 'not affected' : primary?.state === 'risk_accepted' ? 'risk accepted' : 'resolved'}`
              : 'no deadline'
          }}</span>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* prototype .detail-head family, on tokens. Deviation from the prototype (recorded in the
   original PR): the 4px severity side-stripe is dropped — side-stripe accents are a banned
   pattern; severity is carried by the solid chip in the title row instead. */
/* the head band is one of three panels, so the CVSS, EPSS and SLA tiles go under the facts
   (issue 1205, operator 2026-11-16) */
.detail-head {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  padding: 20px 22px;
  box-shadow: var(--shadow);
}
.detail-cve {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.detail-cve h1 {
  font-size: var(--text-detail-mono);
  font-family: var(--font-mono);
  letter-spacing: -0.01em;
  margin: 0;
}
.kev-lg {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--kev-fg);
  background: var(--kev-bg);
  padding: 4px 9px;
  border-radius: var(--r-chip);
}
.detail-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 14px 28px;
  margin-top: 18px;
}
.fact {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.detail-meta em {
  font-style: normal;
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--soft);
}
.fact-val {
  font-size: var(--text-body);
  color: var(--ink);
}
.fact-link {
  text-decoration: none;
  transition: color var(--dur-quick);
}
.fact-link:hover {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.fact-link:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.fact-go {
  color: var(--dash-muted);
  margin-left: 3px;
  vertical-align: -1px;
}
.fact-link:hover .fact-go {
  color: var(--coral-text);
}

/* the risk band: one joined card, hairline-divided cells, urgency carried by the numerals
   (stat-card grammar per the operator's Nuxt UI reference — ours, on tokens) */
.risk-band {
  flex: none;
  align-self: stretch;
  display: flex;
  align-items: stretch;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--card);
}
.risk-cell {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
  padding: 12px 16px;
  min-width: 0;
}
.risk-cell + .risk-cell {
  border-left: 1px solid var(--line2);
}
.risk-label {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--soft);
}
.risk-num {
  font-size: var(--text-kpi);
  font-weight: 600;
  letter-spacing: -0.03em;
  color: var(--ink);
  font-variant-numeric: tabular-nums;
  line-height: 1.15;
}
.risk-num em {
  font-style: normal;
  font-size: var(--text-body);
  color: var(--soft);
}
.risk-num-critical,
.risk-num-over {
  color: var(--sev-critical-fg);
}
.risk-num-high,
.risk-num-tight {
  color: var(--sla-tight-fg);
}
.risk-num-quiet {
  color: var(--soft);
  font-weight: 400;
}
.risk-sub {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--ink);
  margin-top: 2px;
  max-width: 170px;
}
</style>

<script setup lang="ts">
/** Severity mix (prototype MiniBar + MixBar): proportional segments of ONE scanner's severity
 * buckets — never a cross-scanner merge — with the per-severity counts readable on hover
 * (title) and, with `numbers`, as a legend under the bar (tables). Attribution (whose scan)
 * rides the tooltip or the optional inline label. Zero total = muted dash.
 *
 * The legend carries its colour in a swatch and leaves the count in plain ink. Colouring the
 * digits instead cannot work: band fills come from CHART_SEV while text needs the darkened
 * `--sev-*-fg` to clear AA, so the same severity is two different colours and the eye has
 * nothing to match on. One entry per band, in band order — never a fixed four, or a grey
 * negligible band ends up with no number beside it. */
import { computed } from 'vue'

import ScannerTag from '@/components/chips/ScannerTag.vue'
import { fmt } from '@/lib/format'
import { CHART_SEV, type Severity } from '@/styles/tokens'

const SEVERITIES: Severity[] = ['critical', 'high', 'medium', 'low', 'negligible', 'unknown']

const props = defineProps<{
  counts: Partial<Record<Severity, number>>
  /** inline scanner label to the left of the bar (the all-clusters per-scanner stack) */
  label?: string
  /** colored per-severity counts under the bar (the prototype table treatment) */
  numbers?: boolean
  /** whose committed scan these buckets are — named in the tooltip */
  attribution?: string
}>()

const entries = computed(() => SEVERITIES.map((sev) => ({ sev, n: props.counts[sev] ?? 0 })))
const total = computed(() => entries.value.reduce((n, e) => n + e.n, 0))
const segments = computed(() =>
  total.value === 0
    ? null
    : entries.value
        .filter((e) => e.n > 0)
        .map((e) => ({ sev: e.sev, pct: (e.n / total.value) * 100, color: CHART_SEV[e.sev] })),
)
const title = computed(() => {
  const parts = entries.value.filter((e) => e.n > 0).map((e) => `${e.sev} ${fmt(e.n)}`)
  const who = props.attribution ?? props.label
  return `${parts.length ? parts.join(' · ') : 'no findings'}${who ? `, last scan of ${who}` : ''}`
})
</script>

<template>
  <div class="mix" :class="{ 'mix-labeled': label }">
    <div class="mix-row">
      <span v-if="label" class="mix-scanner"><ScannerTag :name="label" /></span>
      <span v-if="segments || numbers" class="mix-bar" :title="title">
        <i v-for="seg in segments ?? []" :key="seg.sev" :style="{ width: `${seg.pct}%`, background: seg.color }" />
      </span>
      <span v-else class="muted-dash" :title="title">-</span>
    </div>
    <span v-if="numbers && segments" class="mix-nums" :title="title">
      <span v-for="seg in segments" :key="seg.sev" class="mix-key">
        <i :style="{ background: seg.color }" />{{ fmt(counts[seg.sev] ?? 0) }}
      </span>
    </span>
  </div>
</template>

<style scoped>
.mix {
  /* the label gutter, shared by the bar row and the count row so the counts sit under the bar
     they describe rather than under the scanner tag. Wide enough for a ScannerTag chip. */
  --mix-label-w: 54px;
  --mix-label-gap: 8px;
}
.mix-row {
  display: flex;
  align-items: center;
  gap: var(--mix-label-gap);
}
/* fixed gutter so the bars line up whatever the tag inside is called */
.mix-scanner {
  width: var(--mix-label-w);
  flex: none;
}
.mix-bar {
  display: flex;
  flex: 1;
  min-width: 90px;
  height: 7px;
  border-radius: 4px;
  overflow: hidden;
  background: var(--meter-track);
}
.mix-bar i {
  height: 100%;
}
.mix-nums {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  margin-top: 6px;
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  line-height: 1;
}
.mix-labeled .mix-nums {
  margin-left: calc(var(--mix-label-w) + var(--mix-label-gap));
}
.mix-key {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-weight: 700;
  color: var(--ink);
}
/* the tie to the band: same fill, same order — the swatch is what carries the severity */
.mix-key i {
  width: 7px;
  height: 7px;
  border-radius: 2px;
  flex: none;
}
</style>

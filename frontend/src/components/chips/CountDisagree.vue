<script setup lang="ts">
/** Per-image count-disagreement pair (prototype `CountDisagree`, D5b): each scanner's finding
 * count under its OWN colored letter chip — never summed — with the delta as an amber badge.
 * Agreement and single-scanner keep the one count they have, but still wear the chips: a number
 * with no scanner on it says nothing about who counted, and one scanner counting alone must not
 * look like two scanners agreeing. */
import { computed } from 'vue'

import { fmt } from '@/lib/format'

const props = defineProps<{
  trivy?: number | null
  grype?: number | null
  total: number
  /** scanners with a committed scan of this digest — the attribution when there is no pair */
  scanners?: string[]
}>()

const SCANNERS = ['trivy', 'grype'] as const
type Scanner = (typeof SCANNERS)[number]
const MARK: Record<Scanner, string> = { trivy: 'T', grype: 'G' }
const LABEL: Record<Scanner, string> = { trivy: 'Trivy', grype: 'Grype' }

const hasPair = computed(() => props.trivy != null && props.grype != null)
const delta = computed(() => (hasPair.value ? props.trivy! - props.grype! : null))

/** A pair proves both scanned; otherwise the row's own scanner list is the only witness. */
const counted = computed<Scanner[]>(() => {
  if (hasPair.value) return [...SCANNERS]
  const seen = new Set((props.scanners ?? []).map((s) => s.toLowerCase()))
  return SCANNERS.filter((s) => seen.has(s))
})

/** The lone witness, when exactly one scanner has counted. */
const only = computed(() => (counted.value.length === 1 ? counted.value[0] : undefined))

const title = computed(() => {
  if (delta.value !== null && delta.value !== 0) {
    const ahead = delta.value > 0 ? LABEL.trivy : LABEL.grype
    return `Trivy found ${fmt(props.trivy!)}, Grype found ${fmt(props.grype!)}. ${ahead} found ${fmt(Math.abs(delta.value))} more.`
  }
  if (delta.value === 0) return `Trivy and Grype report the same number: ${fmt(props.total)}.`
  if (only.value)
    return `Only ${LABEL[only.value]} scanned this digest. It reports ${fmt(props.total)} findings.`
  return `${fmt(props.total)} findings on this digest`
})
</script>

<template>
  <span v-if="delta !== null && delta !== 0" class="cd-split" :title="title">
    <span class="cd-count"><i class="cd-mark" data-scanner="trivy">T</i>{{ fmt(trivy!) }}</span>
    <span class="cd-count"><i class="cd-mark" data-scanner="grype">G</i>{{ fmt(grype!) }}</span>
    <span class="cd-delta">Δ {{ delta > 0 ? '+' : '' }}{{ fmt(delta) }}</span>
  </span>
  <span v-else class="cd-split" :title="title">
    <span v-if="counted.length" class="cd-marks">
      <i v-for="sc in counted" :key="sc" class="cd-mark" :data-scanner="sc">{{ MARK[sc] }}</i>
    </span>
    <span class="cd-count">{{ fmt(total) }}</span>
  </span>
</template>

<style scoped>
.cd-split {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-family: var(--font-mono);
  font-size: var(--text-mono-cell);
  white-space: nowrap;
}
.cd-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 700;
}
/* the two marks touch when they share one count — they are one statement, not two readings */
.cd-marks {
  display: inline-flex;
  gap: 2px;
}
.cd-mark {
  font-style: normal;
  font-size: var(--text-sm);
  font-weight: 700;
  width: 16px;
  height: 16px;
  border-radius: 4px;
  display: inline-grid;
  place-items: center;
}
.cd-mark[data-scanner='trivy'] {
  background: var(--scanner-trivy-bg);
  color: var(--scanner-trivy-fg);
}
.cd-mark[data-scanner='grype'] {
  background: var(--scanner-grype-bg);
  color: var(--scanner-grype-fg);
}
.cd-delta {
  font-size: var(--text-sm);
  font-weight: 700;
  color: var(--health-degraded-fg);
  background: var(--health-degraded-bg);
  padding: 2px 6px;
  border-radius: 4px;
}
</style>

<script setup lang="ts">
/**
 * EPSS mini-bar (prototype `Epss` + `.epss` CSS). Value is the server's raw probability (B-3);
 * null (trivy rows — enrichment is grype-only) renders the muted dash. The ramp colors reference
 * the severity SOLID tokens — this is risk data, not brand.
 */
import { computed } from 'vue'

const props = defineProps<{ v: number | null | undefined }>()

const pct = computed(() => (props.v == null ? 0 : Math.round(props.v * 100)))
const heat = computed(() => (props.v == null ? '' : props.v >= 0.7 ? 'hot' : props.v >= 0.3 ? 'warm' : 'cool'))
</script>

<template>
  <span v-if="v != null" class="epss">
    <span class="epss-bar"><i :data-heat="heat" :style="{ width: pct + '%' }" /></span>
    <span class="epss-num">{{ pct }}%</span>
  </span>
  <span v-else class="muted-dash" title="Only Grype sends the EPSS score.">-</span>
</template>

<style scoped>
.epss {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  justify-content: flex-end;
}
.epss-bar {
  width: 42px;
  height: 5px;
  border-radius: 3px;
  background: var(--meter-track);
  overflow: hidden;
}
.epss-bar i {
  display: block;
  height: 100%;
}
.epss-bar i[data-heat='hot'] {
  background: var(--sev-critical-solid);
}
.epss-bar i[data-heat='warm'] {
  background: var(--sev-high-solid);
}
.epss-bar i[data-heat='cool'] {
  background: var(--muted);
}
.epss-num {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--soft);
  min-width: 30px;
  text-align: right;
}
</style>

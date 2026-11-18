<script setup lang="ts">
/**
 * The Data inspector's head facts: index count, store size and cluster health, read once by
 * the view and passed in.
 */
import AppIcon from '@/components/ui/AppIcon.vue'
import { fmtBytes } from '@/system/inspect'

defineProps<{ indexCount: number | null; storeBytes: number; health: string }>()
</script>

<template>
  <div class="head-facts">
    <p class="head-stat">
      <AppIcon name="layers" :size="15" class="fact-icon" /><template v-if="indexCount != null">{{ indexCount }}</template
      ><span v-else class="muted-dash">-</span><span class="head-unit"> indices</span>
    </p>
    <p class="head-stat">
      <AppIcon name="database" :size="15" class="fact-icon" /><template v-if="storeBytes">{{
        fmtBytes(storeBytes)
      }}</template
      ><span v-else class="muted-dash">-</span><span class="head-unit"> on disk</span>
    </p>
    <p class="head-stat" :class="health ? `health-${health}` : undefined">
      <i v-if="health" class="health-dot" aria-hidden="true" /><template v-if="health">{{ health }}</template
      ><span v-else class="muted-dash">-</span><span class="head-unit"> health</span>
    </p>
  </div>
</template>

<style scoped>
.head-facts {
  display: flex;
  align-items: stretch;
  gap: 28px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
  padding: 12px 22px;
}
.head-facts .head-stat {
  margin: auto 0;
  white-space: nowrap;
  text-align: right;
  display: flex;
  align-items: baseline;
  gap: 7px;
}
.fact-icon {
  align-self: center;
  color: var(--soft);
}
/* the store-health ramp on the ops tokens — hue on word + dot, never bare color-only
   (the dot doubles the signal for the word) */
.health-dot {
  align-self: center;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--health-none-dot);
}
.health-green {
  color: var(--health-ok-fg);
}
.health-green .health-dot {
  background: var(--health-ok-dot);
}
.health-yellow {
  color: var(--health-degraded-fg);
}
.health-yellow .health-dot {
  background: var(--health-degraded-dot);
}
.health-red {
  color: var(--health-down-fg);
}
.health-red .health-dot {
  background: var(--health-down-fg);
}
</style>

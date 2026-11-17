<script setup lang="ts">
/**
 * Risk-acceptance expiry pill (M9d slice 4) — the review queue's status column. Chip
 * language A: quiet workflow tint + lifecycle dot; `expired` speaks in the alarm register
 * because an expired acceptance has already released its findings back to open (D19) — it
 * is the queue's call-to-action. Status derives from the display clock at render, never
 * stored (expiry itself is immutable, D39).
 */
import { computed } from 'vue'

import { daysUntil, expiryStatus } from '@/approvals/viewModel'

const props = defineProps<{ expiry: string | null; nowMs: number }>()

const status = computed(() => expiryStatus(props.expiry, props.nowMs))
const label = computed(() => {
  switch (status.value) {
    case 'open-ended':
      return 'no expiry'
    case 'expired':
      return 'expired'
    case 'expiring': {
      const d = daysUntil(props.expiry as string, props.nowMs)
      return d <= 0 ? 'expires today' : `expires in ${d} day${d === 1 ? '' : 's'}`
    }
    default:
      return 'active'
  }
})
</script>

<template>
  <span class="expiry-tag" :data-status="status">
    <i class="ex-dot" aria-hidden="true" />{{ label }}
  </span>
</template>

<style scoped>
.expiry-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--text-sm);
  font-weight: 500;
  padding: 3px 10px;
  border-radius: 999px;
  white-space: nowrap;
}
.ex-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex: none;
}
.expiry-tag[data-status='open-ended'] { background: var(--line2); color: var(--soft); }
.expiry-tag[data-status='open-ended'] .ex-dot { background: var(--soft); }
.expiry-tag[data-status='active'] { background: var(--state-resolved-bg); color: var(--state-resolved-fg); }
.expiry-tag[data-status='active'] .ex-dot { background: var(--state-resolved-solid); }
.expiry-tag[data-status='expiring'] { background: var(--hist-bg); color: var(--hist-fg); }
.expiry-tag[data-status='expiring'] .ex-dot { background: var(--hist-fg); }
.expiry-tag[data-status='expired'] { background: var(--sev-critical-bg); color: var(--sev-critical-fg); }
.expiry-tag[data-status='expired'] .ex-dot { background: var(--sev-critical-solid); }
</style>

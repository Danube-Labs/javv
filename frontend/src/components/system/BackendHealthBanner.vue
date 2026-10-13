<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import { useHealthStore } from '@/stores/health'

const health = useHealthStore()
// a store that answers but cannot save, or misses part of its data, still serves reads: the
// amber warning line, not the red outage one (operator ruling on the A/B deck, issue 832)
const partial = computed(() => health.reason === 'read-only' || health.reason === 'red')
</script>

<template>
  <Transition name="t-fade">
    <div
      v-if="health.bannerVisible"
      class="sys-line"
      :class="partial ? 'tone-degraded' : 'tone-down'"
      :role="partial ? 'status' : 'alert'"
    >
      <AppIcon :class="{ 'sys-icon': partial }" name="alert" :size="15" />
      <span v-if="health.reason === 'read-only'">The store is read-only: its disk is full. Reads work; changes are not saved.</span>
      <span v-else-if="health.reason === 'red'">Part of the store is not available. Some screens and changes can fail until it recovers.</span>
      <span v-else-if="health.reason === 'backend'">The backend is not answering. Screens cannot load until it is back.</span>
      <span v-else>Search backend unavailable. Check OpenSearch health.</span>
      <button class="dismiss" aria-label="Dismiss" @click="health.dismiss()">
        ×
      </button>
    </div>
  </Transition>
</template>

<style scoped>
.dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: default;
  padding: 4px;
}
</style>

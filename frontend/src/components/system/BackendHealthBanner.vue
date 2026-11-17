<script setup lang="ts">
import { computed } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import UiCloseButton from '@/components/ui/UiCloseButton.vue'
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
      <span v-if="health.reason === 'read-only'">The database is read-only because its disk is full. You can read the data, but JAVV does not save changes.</span>
      <span v-else-if="health.reason === 'red'">Part of the database is not available. Some screens and changes can fail until it recovers.</span>
      <span v-else-if="health.reason === 'backend'">The backend does not answer. Screens cannot load until it answers again.</span>
      <span v-else>The database is not available. Check the health of OpenSearch.</span>
      <UiCloseButton class="dismiss" label="Dismiss" @click="health.dismiss()" />
    </div>
  </Transition>
</template>

<style scoped>
.dismiss {
  margin-left: auto;
}
</style>

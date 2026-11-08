<script setup lang="ts">
/**
 * THE toast renderer — mounted ONCE in AppShell; everything else only talks to the toast
 * store. Ink text on card, hue lives in the icon (never same-hue words on a tint); errors
 * announce assertively, the rest politely.
 */
import AppIcon, { type IconName } from '@/components/ui/AppIcon.vue'
import UiCloseButton from '@/components/ui/UiCloseButton.vue'
import { useToastStore, type ToastKind } from '@/stores/toast'

const toast = useToastStore()
const ICON: Record<ToastKind, IconName> = { success: 'check', error: 'alert', info: 'info' }
</script>

<template>
  <div class="toast-stack">
    <TransitionGroup name="t-toast">
      <div
        v-for="t in toast.toasts"
        :key="t.id"
        class="toast"
        :role="t.kind === 'error' ? 'alert' : 'status'"
      >
        <AppIcon :name="ICON[t.kind]" :size="15" :class="`toast-ic-${t.kind}`" />
        <span class="toast-msg">{{ t.message }}</span>
        <UiCloseButton class="toast-x" label="Dismiss" @click="toast.dismiss(t.id)" />
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 90; /* above the modal backdrop (80) — outcomes show even over a closing dialog */
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.toast {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 320px;
  padding: 10px 12px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
  box-shadow: var(--shadow);
  color: var(--ink);
  font-size: var(--text-body);
}
.toast svg {
  flex: none;
}
.toast-ic-success {
  color: var(--state-resolved-fg);
}
.toast-ic-error {
  color: var(--health-down-fg);
}
.toast-ic-info {
  color: var(--teal-text);
}
.toast-msg {
  flex: 1;
}
</style>

<script setup lang="ts">
/**
 * Topbar user menu (prototype .user-menu grammar): the avatar is the trigger, the panel
 * heads with identity (avatar echo · username · role chip) and carries Settings (gated —
 * the route requires can_manage_settings) and Sign out. Behavior rides UiDropdown
 * (outside-mousedown + Escape + t-pop, the §2 dismiss contract).
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import AppIcon from '@/components/ui/AppIcon.vue'
import UiDropdown from '@/components/ui/UiDropdown.vue'
import { logger } from '@/lib/logger'
import { roleLabel } from '@/lib/roleLabel'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const initials = computed(() => (auth.user?.username ?? '?').slice(0, 2).toUpperCase())
const role = computed(() => roleLabel(auth.user?.role ?? ''))

async function signOut(close: () => void) {
  close()
  logger.info('user_menu_sign_out')
  await auth.logout()
  await router.push({ name: 'login' })
}

function goSettings(close: () => void) {
  close()
  void router.push('/settings')
}
</script>

<template>
  <UiDropdown>
    <template #trigger="{ toggle, open }">
      <button
        type="button"
        class="avatar"
        :class="{ 'avatar-open': open }"
        :aria-label="`Account menu for ${auth.user?.username ?? 'unknown user'}`"
        aria-haspopup="menu"
        :aria-expanded="open"
        @click="toggle"
      >
        {{ initials }}
      </button>
    </template>
    <template #default="{ close }">
      <div class="dd-menu user-menu" role="menu">
        <div class="user-menu-head">
          <span class="avatar avatar-echo" aria-hidden="true">{{ initials }}</span>
          <div class="user-id">
            <b>{{ auth.user?.username }}</b>
            <span class="user-role">{{ role }}</span>
          </div>
        </div>
        <button
          v-if="auth.hasCapability('can_manage_settings')"
          type="button"
          class="dd-item"
          role="menuitem"
          @click="goSettings(close)"
        >
          <AppIcon name="gear" :size="14" />Settings
        </button>
        <button type="button" class="dd-item" role="menuitem" @click="signOut(close)">
          <AppIcon name="rewind" :size="14" />Sign out
        </button>
      </div>
    </template>
  </UiDropdown>
</template>

<style scoped>
.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 50%;
  background: var(--slate2);
  color: var(--side-brand-fg);
  font-family: var(--font-ui);
  font-size: var(--text-sm);
  font-weight: 600;
  cursor: default;
}
.avatar:hover,
.avatar-open {
  box-shadow: 0 0 0 2px var(--card), 0 0 0 4px var(--line2);
}
.avatar:active {
  background: var(--slate);
}
.dd-menu {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 30;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--dd-shadow);
  padding: 5px;
  min-width: 230px;
}
.user-menu-head {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line2);
  margin-bottom: 5px;
}
.avatar-echo {
  width: 34px;
  height: 34px;
}
.user-id b {
  display: block;
  font-size: var(--text-control);
}
.user-role {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--teal-text);
  background: var(--note-info-bg);
  padding: 2px 7px;
  border-radius: 5px;
  display: inline-block;
  margin-top: 3px;
  text-transform: capitalize;
}
.dd-item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  border: 1px solid transparent;
  background: transparent;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  text-align: left;
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: var(--text-body);
  cursor: default;
}
.dd-item:hover {
  background: var(--row-hover);
  border-color: var(--line2);
}
.dd-item:active {
  background: var(--line2);
}
.dd-item svg {
  color: var(--soft);
}
</style>

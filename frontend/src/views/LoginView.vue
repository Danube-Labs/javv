<script setup lang="ts">
/**
 * Login + forced password change (SCREENS §0). Error copy is GENERIC — never a
 * user-existence hint; 429 lockout copy gives no countdown oracle. A must_change session is
 * locked here (mode 'change') until the password is rotated (SEC-6). A server that does not
 * answer is said as such, never as a wrong password; the page keeps asking, and a visitor whose
 * session is still good goes straight back in when the server returns (issue 675).
 */
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import icon from '@/assets/brand/icon.svg'
import {
  PASSWORD_MIN_LENGTH,
  passwordLength,
  SERVER_DOWN_COPY,
  useAuthStore,
} from '@/stores/auth'
import { POLL_MS, useHealthStore } from '@/stores/health'

const auth = useAuthStore()
const router = useRouter()

const username = ref('')
const password = ref('')
const newPassword = ref('')
const confirm = ref('')
const error = ref<string | null>(null)
const busy = ref(false)

const mode = computed(() => (auth.mustChange ? 'change' : 'login'))
// a forced change that ends in sign-in must not leave the current password in the sign-in field
watch(mode, (now) => {
  if (now === 'login') password.value = newPassword.value = confirm.value = ''
})

const health = useHealthStore()
let recheck: ReturnType<typeof setInterval> | 0 = 0
async function checkAgain() {
  await health.check()
  if (health.degraded) return
  await auth.fetchMe()
  if (auth.isAuthed && !auth.mustChange) await router.push('/overview')
}
watch(
  () => auth.unreachable,
  (down) => {
    if (recheck) clearInterval(recheck)
    recheck = down ? setInterval(() => void checkAgain(), POLL_MS) : 0
  },
  { immediate: true },
)
onUnmounted(() => {
  if (recheck) clearInterval(recheck)
})

async function submitLogin() {
  busy.value = true
  error.value = await auth.login(username.value, password.value)
  busy.value = false
  if (error.value === null && !auth.mustChange) await router.push('/overview')
}

async function submitChange() {
  if (passwordLength(newPassword.value) < PASSWORD_MIN_LENGTH) {
    error.value = `The new password needs at least ${PASSWORD_MIN_LENGTH} characters.`
    return
  }
  if (newPassword.value !== confirm.value) {
    error.value = 'New passwords do not match.'
    return
  }
  busy.value = true
  error.value = await auth.changePassword(password.value, newPassword.value)
  busy.value = false
  if (error.value === null) await router.push('/overview')
}
</script>

<template>
  <main class="login-page">
    <form class="card" @submit.prevent="mode === 'login' ? submitLogin() : submitChange()">
      <div class="login-brand">
        <img :src="icon" alt="" width="44" height="44" />
        <span class="brand-word"><b>javv</b><span>by Danube Labs</span></span>
      </div>
      <p class="tagline">just another vulnerability viewer</p>

      <template v-if="mode === 'login'">
        <label for="username">Username</label>
        <input class="set-input" id="username" v-model="username" autocomplete="username" required />
        <label for="password">Password</label>
        <input class="set-input" id="password" v-model="password" type="password" autocomplete="current-password" required />
      </template>

      <template v-else>
        <p class="notice">Your password must be changed before continuing.</p>
        <label for="current">Current password</label>
        <input class="set-input" id="current" v-model="password" type="password" autocomplete="current-password" required />
        <label for="new">New password</label>
        <input
          id="new"
          class="set-input"
          v-model="newPassword"
          type="password"
          autocomplete="new-password"
          aria-describedby="password-rule"
          required
        />
        <label for="confirm">Confirm new password</label>
        <input class="set-input" id="confirm" v-model="confirm" type="password" autocomplete="new-password" required />
        <p id="password-rule" class="rule">
          At least {{ PASSWORD_MIN_LENGTH }} characters. Your current password stops working once
          you set the new one.
        </p>
      </template>

      <p v-if="auth.unreachable" class="error" role="alert">{{ SERVER_DOWN_COPY }}</p>
      <p v-else-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" :disabled="busy">
        {{ mode === 'login' ? 'Sign in' : 'Change password' }}
      </button>
      <p v-if="mode === 'login'" class="note">
        Forgot your password? Ask an admin to reset it. If no admin can sign in, see
        <em>A forgotten password</em> in the Deploying guide.
      </p>
    </form>
  </main>
</template>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}
.card {
  display: flex;
  flex-direction: column;
  width: 340px;
  padding: 28px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 11px;
}
.brand-word {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}
.brand-word b {
  font-size: var(--text-brand-word);
  letter-spacing: -0.03em;
}
.brand-word span {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  color: var(--soft);
  letter-spacing: 0.04em;
  margin-top: 2px;
}
.tagline {
  margin: 2px 0 18px;
  color: var(--soft);
  font-size: var(--text-body);
}
.notice {
  padding: 8px 10px;
  margin: 0 0 12px;
  background: var(--hist-bg);
  color: var(--ink);
  border: 1px solid var(--hist-line);
  border-radius: var(--r-chip);
  font-size: var(--text-body);
}
label {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--soft);
  margin: 10px 0 4px;
}
.rule {
  margin: 10px 0 0;
  color: var(--soft);
  font-size: var(--text-sm);
  line-height: 1.5;
}
.note {
  margin: 16px 0 0;
  color: var(--soft);
  font-size: var(--text-sm);
  line-height: 1.5;
  text-align: center;
}
.error {
  margin: 12px 0 0;
  color: var(--health-down-fg);
  font-size: var(--text-body);
}
button {
  margin-top: 18px;
  padding: 9px;
  border: none;
  border-radius: var(--r-sm);
  background: var(--slate2); /* the primary fill of UiButton (issue 1004) */
  color: var(--card);
  font-family: var(--font-ui);
  font-size: var(--text-body);
  font-weight: 600;
  cursor: default;
  transition: background 0.12s;
}
button:hover:not(:disabled) {
  background: var(--slate);
}
button:disabled {
  opacity: 0.6;
  cursor: default;
}
</style>

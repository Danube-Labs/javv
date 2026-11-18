<script setup lang="ts">
/**
 * Users & roles panel (§13.6; prototype screens-config.jsx `users` section). Ruled prototype
 * deltas (row 8/A-4): DISABLE, never delete (no delete API — the trash icon is gone); "Invite"
 * = create-with-temp-password (the user must change it at first login, SEC-6); the roles card
 * renders the capability BUNDLES from `system-roles` content (not the v4 5-role matrix) so a
 * seeded 5th role appears without a client change. A role change REVOKES the user's sessions
 * (D33) — the confirm dialog says so. 409 on the last enabled admin renders inline.
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import {
  createUserApiV1AdminUsersPost,
  listRolesApiV1AdminRolesGet,
  listUsersApiV1AdminUsersGet,
  passwordResetApiV1AdminUsersUsernamePasswordResetPost,
  setDisabledApiV1AdminUsersUsernameDisabledPatch,
  setRoleApiV1AdminUsersUsernameRolePatch,
} from '@/api/generated'
import { client } from '@/api/client'
import { detailOr } from '@/api/problem'
import DotWord from '@/components/chips/DotWord.vue'
import GridPager from '@/components/findings/GridPager.vue'
import RolesCard, { type PermissionRow, type RoleRow } from '@/components/settings/RolesCard.vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSelect from '@/components/ui/UiSelect.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { usePagedSlice } from '@/composables/usePagedSlice'
import { logger } from '@/lib/logger'
import { roleLabel } from '@/lib/roleLabel'
import { useAuthStore } from '@/stores/auth'
import { useToastStore } from '@/stores/toast'

interface UserRow {
  username: string
  role: string
  capabilities: string[]
  must_change: boolean
  disabled: boolean
  auth_source: string
  created_at: string | null
}

const auth = useAuthStore()
const toast = useToastStore()
const router = useRouter()

/** Sign-in history for these accounts, as a canned audit lens rather than a card: failed logins
 * are not journaled, so a card counting sign-ins here would report a half-truth. */
function goSignIns() {
  void router.push({ name: 'audit', query: { action: 'login' } })
}

const users = ref<UserRow[]>([])
const roles = ref<RoleRow[]>([])
const permissions = ref<PermissionRow[]>([])
const loading = ref(true)
const failed = ref(false)
const busy = ref(false)

async function load() {
  loading.value = true
  const [u, r] = await Promise.all([
    listUsersApiV1AdminUsersGet({ client, query: { size: 1000 } }),
    listRolesApiV1AdminRolesGet({ client }),
  ])
  loading.value = false
  failed.value = !u.response?.ok || !r.response?.ok || !u.data || !r.data
  if (failed.value) {
    logger.warn('users_load_failed', { users: u.response?.status, roles: r.response?.status })
    return
  }
  users.value = (u.data as { users: UserRow[] }).users
  const body = r.data as { roles: RoleRow[]; permissions?: PermissionRow[] }
  roles.value = body.roles
  permissions.value = body.permissions ?? []
}
void load()

// the list is read again after an invite, a role change or a disable: the page stays (issue 1190)
const { page, size, shown, hasNext, setSize } = usePagedSlice(() => users.value, 10, { keepPage: true })

// ── invite (create-with-temp-password) ─────────────────────────────────────────────────
const inviteOpen = ref(false)
const inviteName = ref('')
const invitePassword = ref('')
const inviteRole = ref('viewer')
const inviteError = ref('')

function openInvite() {
  inviteName.value = ''
  invitePassword.value = ''
  inviteRole.value = 'viewer'
  inviteError.value = ''
  inviteOpen.value = true
}

async function submitInvite() {
  busy.value = true
  const { error, response } = await createUserApiV1AdminUsersPost({
    client,
    body: { username: inviteName.value.trim(), temp_password: invitePassword.value, role: inviteRole.value },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('user_create_failed', { status: response?.status })
    inviteError.value = detailOr(
      error,
      'JAVV refused the username. A username has 3 to 64 lower-case letters, digits, dots, underscores or hyphens. You cannot use system or fleet.',
    )
    return
  }
  inviteOpen.value = false
  toast.success(`JAVV created ${inviteName.value.trim()}. They must change the temporary password when they first sign in.`)
  await load()
}

// ── role change (confirm: revokes sessions) ─────────────────────────────────────────────
const roleChange = ref<{ user: UserRow; to: string } | null>(null)
const rowError = ref<{ username: string; message: string } | null>(null)

function onRolePick(user: UserRow, to: string) {
  if (to !== user.role) roleChange.value = { user, to }
}

async function submitRoleChange() {
  const change = roleChange.value
  if (change === null) return
  busy.value = true
  const { error, response } = await setRoleApiV1AdminUsersUsernameRolePatch({
    client,
    path: { username: change.user.username },
    body: { role: change.to },
  })
  busy.value = false
  roleChange.value = null
  if (!response?.ok) {
    logger.warn('role_change_failed', { status: response?.status })
    rowError.value = {
      username: change.user.username,
      message: detailOr(error, 'JAVV did not change the role. Nothing changed.'),
    }
    await load() // resets the select to the server truth
    return
  }
  rowError.value = null
  toast.success(`${change.user.username} is now ${roleLabel(change.to)}. JAVV ended their sessions.`)
  await load()
}

// ── disable / enable ────────────────────────────────────────────────────────────────────
const disableTarget = ref<UserRow | null>(null)

async function setDisabled(user: UserRow, disabled: boolean) {
  busy.value = true
  const { error, response } = await setDisabledApiV1AdminUsersUsernameDisabledPatch({
    client,
    path: { username: user.username },
    body: { disabled },
  })
  busy.value = false
  disableTarget.value = null
  if (!response?.ok) {
    logger.warn('user_disable_failed', { status: response?.status })
    rowError.value = {
      username: user.username,
      message: detailOr(error, 'JAVV did not make the change. Nothing changed.'),
    }
    return
  }
  rowError.value = null
  toast.success(disabled ? `JAVV disabled ${user.username} and ended their sessions.` : `JAVV enabled ${user.username} again.`)
  await load()
}

// ── password reset ──────────────────────────────────────────────────────────────────────
const resetTarget = ref<UserRow | null>(null)
const resetPassword = ref('')
const resetError = ref('')

function openReset(user: UserRow) {
  resetPassword.value = ''
  resetError.value = ''
  resetTarget.value = user
}

async function submitReset() {
  if (resetTarget.value === null) return
  busy.value = true
  const { error, response } = await passwordResetApiV1AdminUsersUsernamePasswordResetPost({
    client,
    path: { username: resetTarget.value.username },
    body: { temp_password: resetPassword.value },
  })
  busy.value = false
  if (!response?.ok) {
    logger.warn('pwd_reset_failed', { status: response?.status })
    resetError.value = detailOr(error, 'JAVV did not reset the password. The old password still works.')
    return
  }
  toast.success(`${resetTarget.value.username} must change the new temporary password when they next sign in.`)
  resetTarget.value = null
}

const isSelf = (user: UserRow) => user.username === auth.user?.username
</script>

<template>
  <div class="stack">
    <SettingsCard
      title="Users"
      subtitle="Each user has one role. The backend checks the role on each request, not only the screens."
    >
      <template #action>
        <span class="head-actions">
          <UiButton @click="goSignIns"><AppIcon name="clock" :size="13" />Recent sign-ins</UiButton>
          <UiButton :disabled="busy" @click="openInvite"><AppIcon name="plus" :size="13" />Invite user</UiButton>
        </span>
      </template>

      <UiSkeleton
        v-if="loading"
        :height="160"
        radius="sm"
        label="Loading users"
        class="skel-gap"
      />
      <p v-else-if="failed" class="load-error" role="alert">
        JAVV cannot show the user list. Check the backend connection.
      </p>

      <div v-if="!loading && !failed" class="set-flush">
      <div class="tbl-wrap">
        <table class="tbl tbl-dense tbl-quiet tbl-hover">
          <thead>
            <tr>
              <th>User</th>
              <th class="fit">Role</th>
              <th class="fit">Source</th>
              <th class="fit">Status</th>
              <th class="fit"></th>
            </tr>
          </thead>
          <tbody>
            <template v-for="user in shown" :key="user.username">
              <tr :class="{ 'row-off': user.disabled }">
                <td>
                  <span class="mono-cell sm">{{ user.username }}</span>
                  <span v-if="isSelf(user)" class="self-tag">you</span>
                </td>
                <td class="fit">
                  <UiSelect
                    row
                    :model-value="user.role"
                    :disabled="busy || user.disabled"
                    :aria-label="`Role for ${user.username}`"
                    @update:model-value="onRolePick(user, $event)"
                  >
                    <option v-for="r in roles" :key="r.role" :value="r.role">{{ roleLabel(r.role) }}</option>
                  </UiSelect>
                </td>
                <td class="fit">{{ user.auth_source }}</td>
                <td class="fit">
                  <DotWord v-if="user.disabled" tone="muted" label="disabled" />
                  <DotWord v-else-if="user.must_change" tone="warn" label="must change password" />
                  <DotWord v-else tone="ok" label="active" />
                </td>
                <td class="fit">
                  <span class="row-actions">
                    <UiButton
                      :disabled="busy || user.auth_source !== 'local' || user.disabled"
                      :title="user.auth_source !== 'local' ? 'Password is managed by the identity provider' : undefined"
                      @click="openReset(user)"
                    >Reset password</UiButton>
                    <UiButton v-if="user.disabled" :disabled="busy" @click="setDisabled(user, false)">Enable</UiButton>
                    <UiButton v-else :disabled="busy" @click="disableTarget = user">Disable</UiButton>
                  </span>
                </td>
              </tr>
              <tr v-if="rowError?.username === user.username">
                <td colspan="5" class="row-error" role="alert">{{ rowError.message }}</td>
              </tr>
            </template>
          </tbody>
        </table>
        <GridPager
          :total="users.length"
          :page="page"
          :size="size"
          :shown="shown.length"
          :has-prev="page > 0"
          :has-next="hasNext"
          @prev="page -= 1"
          @next="page += 1"
          @update:size="setSize"
        />
      </div>
      </div>
    </SettingsCard>

    <RolesCard :roles="roles" :permissions="permissions" :ready="!loading && !failed" />

    <!-- invite -->
    <ModalShell v-if="inviteOpen" title="Invite a user" subtitle="The user signs in with the temporary password and must change it." @close="inviteOpen = false">
      <UiField label="Username" first hint="Use 3 to 64 lower-case letters, digits, dots, underscores or hyphens." for="inv-name">
        <SettingsInput id="inv-name" v-model="inviteName" />
      </UiField>
      <UiField label="Temporary password" hint="The backend checks it against the password policy. The user must change it at the first sign-in." for="inv-pass">
        <SettingsInput id="inv-pass" v-model="invitePassword" />
      </UiField>
      <UiField label="Role" for="inv-role">
        <UiSelect id="inv-role" v-model="inviteRole">
          <option v-for="r in roles" :key="r.role" :value="r.role">{{ roleLabel(r.role) }}</option>
        </UiSelect>
      </UiField>
      <p v-if="inviteError" class="modal-error" role="alert">{{ inviteError }}</p>
      <template #actions>
        <UiButton variant="ghost" @click="inviteOpen = false">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy || !inviteName.trim() || !invitePassword" @click="submitInvite">
          {{ busy ? 'Creating…' : 'Create user' }}
        </UiButton>
      </template>
    </ModalShell>

    <!-- role-change confirm -->
    <ModalShell v-if="roleChange" title="Change role?" @close="roleChange = null; void load()">
      <p class="confirm-copy">
        <span class="mono-cell sm">{{ roleChange.user.username }}</span> becomes
        <b>{{ roleLabel(roleChange.to) }}</b>. Their permissions change at once. JAVV <b>signs out
        each active session</b>, so an old session never keeps the old role.
      </p>
      <template #actions>
        <UiButton variant="ghost" @click="roleChange = null; void load()">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy" @click="submitRoleChange">
          {{ busy ? 'Changing…' : 'Change role' }}
        </UiButton>
      </template>
    </ModalShell>

    <!-- disable confirm -->
    <ModalShell v-if="disableTarget" title="Disable this user?" @close="disableTarget = null">
      <p class="confirm-copy">
        JAVV signs <span class="mono-cell sm">{{ disableTarget.username }}</span> out of each session.
        The user cannot sign in after that. JAVV deletes nothing: the history still shows their
        triage, and you can enable the user again at any time.<template v-if="isSelf(disableTarget)"> <b>This is your own account.</b></template>
      </p>
      <template #actions>
        <UiButton variant="ghost" @click="disableTarget = null">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy" @click="setDisabled(disableTarget, true)">
          {{ busy ? 'Disabling…' : 'Disable' }}
        </UiButton>
      </template>
    </ModalShell>

    <!-- password reset -->
    <ModalShell
      v-if="resetTarget"
      :title="`Reset ${resetTarget.username}'s password`"
      subtitle="JAVV ends their sessions. They must change the temporary password at the next sign-in."
      @close="resetTarget = null"
    >
      <UiField label="Temporary password" first hint="The backend checks it against the password policy." for="rst-pass">
        <SettingsInput id="rst-pass" v-model="resetPassword" />
      </UiField>
      <p v-if="resetError" class="modal-error" role="alert">{{ resetError }}</p>
      <template #actions>
        <UiButton variant="ghost" @click="resetTarget = null">Cancel</UiButton>
        <UiButton variant="primary" :disabled="busy || !resetPassword" @click="submitReset">
          {{ busy ? 'Resetting…' : 'Reset password' }}
        </UiButton>
      </template>
    </ModalShell>
  </div>
</template>

<style scoped>
.self-tag {
  margin-left: 8px;
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--teal-text);
  background: var(--note-info-bg);
  padding: 2px 6px;
  border-radius: 5px;
}
.row-off td {
  color: var(--soft);
}
.row-error {
  color: var(--health-down-fg);
  font-size: var(--text-sm);
}
.load-error {
  margin: 14px 0 8px;
}
.skel-gap {
  margin: 14px 0 8px;
}
</style>

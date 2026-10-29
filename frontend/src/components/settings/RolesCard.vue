<script setup lang="ts">
/**
 * The Roles card: one table, a row for each permission and a column for each role (issue 990,
 * option A). Roles and permissions both come from GET /api/v1/admin/roles, so a role or a
 * permission seeded later shows without a client change. Display-only.
 */
import { computed } from 'vue'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { roleLabel } from '@/lib/roleLabel'

export interface RoleRow {
  role: string
  capabilities: string[]
}

export interface PermissionRow {
  id: string
  name: string
  description: string
}

const props = defineProps<{ roles: RoleRow[]; permissions: PermissionRow[]; ready: boolean }>()

const ALL = '*'
const holdsAll = (r: RoleRow) => r.capabilities.includes(ALL)

// fewest permissions first, so the columns read from viewer to admin
const columns = computed(() =>
  [...props.roles].sort((a, b) => (holdsAll(a) ? Infinity : a.capabilities.length) - (holdsAll(b) ? Infinity : b.capabilities.length)),
)

// a permission a role holds but the server does not list still gets a row, named by its id
const rows = computed<PermissionRow[]>(() => {
  const known = new Set(props.permissions.map((p) => p.id))
  const unknown = [...new Set(props.roles.flatMap((r) => r.capabilities))].filter((c) => c !== ALL && !known.has(c))
  return [...props.permissions, ...unknown.map((id) => ({ id, name: id, description: '' }))]
})

const has = (r: RoleRow, id: string) => holdsAll(r) || r.capabilities.includes(id)
</script>

<template>
  <SettingsCard title="Roles" subtitle="What each role can do. Every role can read the findings, images and dashboards.">
    <div v-if="ready" class="tbl-wrap roles-wrap">
      <table class="tbl tbl-dense tbl-hover">
        <thead>
          <tr>
            <th>Permission</th>
            <th v-for="r in columns" :key="r.role" class="c">{{ roleLabel(r.role) }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in rows" :key="p.id">
            <td>
              <div class="perm-name">{{ p.name }}</div>
              <div v-if="p.description" class="perm-does">{{ p.description }}</div>
            </td>
            <td v-for="r in columns" :key="r.role" class="c">
              <span v-if="has(r, p.id)" role="img" class="perm-yes" :aria-label="`${roleLabel(r.role)}: yes`">
                <AppIcon name="check" :size="15" />
              </span>
              <span v-else role="img" class="perm-no" :aria-label="`${roleLabel(r.role)}: no`">–</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="roles-note">
      The admin role has every permission, also the permissions of later releases. To remove a person's access,
      disable the user. JAVV keeps the user, so the Audit log still shows who did each change.
    </p>
  </SettingsCard>
</template>

<style scoped>
.roles-wrap {
  margin-top: 10px;
}
.perm-name {
  font-weight: 600;
  color: var(--ink);
}
.perm-does {
  margin-top: 2px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.perm-yes {
  color: var(--teal);
}
.perm-no {
  color: var(--soft);
}
.roles-note {
  margin: 12px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
</style>

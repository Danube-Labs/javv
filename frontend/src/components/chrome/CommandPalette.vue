<script setup lang="ts">
/**
 * ⌘K command palette (M9f slice 2 — issue 319 ruling: Nuxt UI CommandPalette grammar on JAVV
 * tokens, replacing the disabled topbar input). Two result families:
 * — Screens: the shared nav model filtered by label (client — it's a static list);
 * — CVEs / images / namespaces: server-aggregated buckets from useGlobalSearch (§15 —
 *   composed findings-groups queries, counts are server counts, never client-derived).
 * Every hit lands on a pre-filtered Findings grid via the existing fromQuery vocabulary.
 * Dismiss contract as ModalShell (Escape, outside-click); ↑↓ + Enter drive the list.
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { visibleNav, type NavItem } from '@/components/chrome/navModel'
import AppIcon, { type IconName } from '@/components/ui/AppIcon.vue'
import { MIN_CHARS, useGlobalSearch } from '@/composables/useGlobalSearch'
import { useAuthStore } from '@/stores/auth'
import { useClusterStore } from '@/stores/cluster'

const emit = defineEmits<{ close: [] }>()

const router = useRouter()
const auth = useAuthStore()
const clusterStore = useClusterStore()
const { results, searching, failed, search } = useGlobalSearch(() => clusterStore.selectedId)

const text = ref('')
const inputEl = ref<HTMLInputElement | null>(null)
onMounted(() => void nextTick(() => inputEl.value?.focus()))

/* ---- the flattened, keyboard-walkable row list ---- */
interface Row {
  group: string
  icon: IconName
  label: string
  count?: number
  go: () => void
}

const screens = computed<NavItem[]>(() => {
  const q = text.value.trim().toLowerCase()
  const items = visibleNav(auth.hasCapability).flatMap((g) => g.items)
  return q ? items.filter((i) => i.label.toLowerCase().includes(q)) : items
})

const rows = computed<Row[]>(() => [
  ...screens.value.map((s) => ({
    group: 'Screens',
    icon: s.icon, // the sidebar's own icon for the screen: one nav model, one picture
    label: s.label,
    go: () => void router.push(s.to),
  })),
  ...results.value.cves.map((b) => ({
    group: 'CVEs',
    icon: 'alert' as const,
    label: b.key,
    count: b.count,
    go: () => void router.push({ path: '/findings', query: { q: b.key } }),
  })),
  ...results.value.images.map((b) => ({
    group: 'Images',
    icon: 'cube' as const,
    label: b.key,
    count: b.count,
    go: () => void router.push({ path: '/findings', query: { image: b.key } }),
  })),
  ...results.value.namespaces.map((b) => ({
    group: 'Namespaces',
    icon: 'layers' as const,
    label: b.key,
    count: b.count,
    go: () => void router.push({ path: '/findings', query: { namespace: b.key } }),
  })),
])

const active = ref(0)
watch(text, (t) => {
  active.value = 0
  search(t)
})

const serverEmpty = computed(
  () =>
    text.value.trim().length >= MIN_CHARS &&
    !searching.value &&
    !failed.value &&
    results.value.cves.length + results.value.images.length + results.value.namespaces.length ===
      0,
)

function pick(row: Row) {
  row.go()
  emit('close')
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') return emit('close')
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = Math.min(active.value + 1, rows.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = Math.max(active.value - 1, 0)
  } else if (e.key === 'Enter') {
    const row = rows.value[active.value]
    if (row) pick(row)
  }
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Transition name="t-modal" appear>
    <div class="cp-backdrop" @click.self="emit('close')">
      <div class="cp" role="dialog" aria-modal="true" aria-label="Global search">
        <div class="cp-input-row">
          <AppIcon name="search" :size="15" />
          <!-- eslint-disable-next-line vue/no-restricted-html-elements -- the palette keeps its own search row, with the cursor in it on open (issue 1053) -->
          <input
            ref="inputEl"
            v-model="text"
            type="text"
            placeholder="Search CVE, image, namespace, or jump to a screen…"
            aria-label="Global search"
          />
          <kbd>esc</kbd>
        </div>

        <div class="cp-list" role="listbox" aria-label="Results">
          <template v-for="(row, i) in rows" :key="`${row.group}:${row.label}`">
            <p v-if="i === 0 || rows[i - 1]?.group !== row.group" class="cp-group">
              {{ row.group }}
            </p>
            <button
              type="button"
              class="cp-row"
              :class="{ active: i === active }"
              role="option"
              :aria-selected="i === active"
              @mousemove="active = i"
              @click="pick(row)"
            >
              <AppIcon :name="row.icon" :size="14" />
              <span class="cp-label" :class="{ mono: row.group !== 'Screens' }">{{ row.label }}</span>
              <span v-if="row.count !== undefined" class="cp-count">{{ row.count }}</span>
              <AppIcon class="cp-go" name="chevron" :size="11" />
            </button>
          </template>

          <p v-if="searching" class="cp-note" role="status">Searching…</p>
          <p v-else-if="failed" class="cp-error" role="alert">
            Search unavailable. Check the backend connection.
          </p>
          <p v-else-if="serverEmpty && rows.length === 0" class="cp-note" role="status">
            No matches for “{{ text.trim() }}” in this cluster.
          </p>
          <p v-else-if="text.trim().length < MIN_CHARS" class="cp-note">
            Type {{ MIN_CHARS }}+ characters to search findings. Results are scoped to the
            selected cluster.
          </p>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.cp-backdrop {
  position: fixed;
  inset: 0;
  background: var(--backdrop);
  z-index: 60;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 12vh 16px 0;
}
.cp {
  width: min(560px, 100%);
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--dd-shadow);
  overflow: hidden;
}
.cp-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line2);
  color: var(--soft);
}
.cp-input-row input {
  flex: 1;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: var(--text-body);
}
.cp-input-row input::placeholder {
  color: var(--soft);
}
.cp-input-row kbd {
  font-family: var(--font-mono);
  font-size: var(--text-facet-label);
  text-transform: uppercase;
  border: 1px solid var(--line2);
  border-radius: var(--r-chip);
  padding: 2px 6px;
  color: var(--soft);
}
.cp-list {
  max-height: 46vh;
  overflow-y: auto;
  padding: 6px;
}
.cp-group {
  margin: 8px 8px 4px;
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--soft);
}
.cp-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: 1px solid transparent;
  border-radius: var(--r-sm);
  background: transparent;
  padding: 8px 10px;
  color: var(--ink);
  font-family: var(--font-ui);
  font-size: var(--text-dd-item);
  text-align: left;
  cursor: default;
}
.cp-row.active {
  background: var(--row-hover);
  border-color: var(--line2);
}
.cp-row:active {
  background: var(--line2);
}
.cp-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cp-label.mono {
  font-family: var(--font-mono);
  font-size: var(--text-mono-cell);
}
.cp-count {
  font-family: var(--font-mono);
  font-size: var(--text-facet-count);
  color: var(--soft);
}
.cp-go {
  color: var(--dash-muted);
}
.cp-row.active .cp-go {
  color: var(--coral-text);
}
.cp-note,
.cp-error {
  margin: 10px 8px;
  font-size: var(--text-sm);
  color: var(--soft);
}
.cp-error {
  color: var(--health-down-fg);
}
</style>

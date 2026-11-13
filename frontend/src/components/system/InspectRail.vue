<script setup lang="ts">
/**
 * The inspector's index rail (issue 406 — extracted panel, F-15 size rule): INDEX-MAP-grouped
 * indices from `_cat/indices`; a click hands the pattern to the console. Credential indices
 * never reach this list (filtered in system/inspect.ts to mirror the backend denial).
 */
import { fmtDocs, splitMiddle, type RailEntry, type RailGroups } from '@/system/inspect'

defineProps<{ groups: RailGroups; activePattern: string; failed: boolean }>()
const emit = defineEmits<{ pick: [pattern: string] }>()

const SECTIONS: { key: keyof RailGroups; label: string }[] = [
  { key: 'history', label: 'append history' },
  { key: 'state', label: 'materialized state' },
  { key: 'system', label: 'system' },
]

function entries(groups: RailGroups, key: keyof RailGroups): RailEntry[] {
  return groups[key]
}
</script>

<template>
  <aside class="card rail" aria-label="Indices">
    <h2 class="panel-band">Indices</h2>
    <p v-if="failed" class="load-error" role="alert">
      Index list unavailable. The console still works with a typed path.
    </p>
    <template v-else>
      <div v-for="s in SECTIONS" :key="s.key" class="rail-group">
        <template v-if="entries(groups, s.key).length">
          <span>{{ s.label }}</span>
          <button
            v-for="e in entries(groups, s.key)"
            :key="e.pattern"
            type="button"
            class="idx"
            :class="{ on: activePattern === e.pattern }"
            @click="emit('pick', e.pattern)"
          >
            <span class="idx-name" :title="e.pattern"
              ><span class="idx-head">{{ splitMiddle(e.pattern).head }}</span
              ><span class="idx-tail">{{ splitMiddle(e.pattern).tail }}</span></span
            >{{ ' ' }}<i>{{ fmtDocs(e.docs) }}</i>
          </button>
        </template>
      </div>
      <p class="rail-foot">
        Counts from <code>_cat/indices</code>; credential indices are not inspectable.
        Click inserts the pattern.
      </p>
    </template>
  </aside>
</template>

<style scoped>
.rail {
  padding: 0 0 8px;
  overflow: hidden;
}
/* the B2 slate table-head band (base.css .tbl thead ruling) as the card's title register */
.panel-band {
  margin: 0;
  padding: 10px 16px;
  background: var(--table-head-bg);
  color: var(--table-head-fg);
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.rail-group:not(:empty) {
  padding: 8px 8px 4px;
}
.rail-group:not(:empty) ~ .rail-group:not(:empty) {
  border-top: 1px solid var(--line2);
}
.rail-group > span {
  display: block;
  padding: 2px 8px 6px;
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--soft);
}
.idx {
  display: flex;
  width: 100%;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
  padding: 5px 8px;
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  background: transparent;
  font-family: var(--font-mono);
  font-size: var(--text-mono-cell);
  color: var(--ink);
  text-align: left;
  cursor: default;
}
.idx:hover {
  background: var(--control-hover-bg);
  border-color: var(--control-hover-line);
}
.idx:active {
  background: var(--control-active-bg);
}
.idx.on {
  background: var(--dd-on-bg);
  border-color: var(--coral);
}
/* a long name truncates in the middle and keeps its ending, its full text in the title (EUI's
   middle truncation for identifiers, issue 652) */
.idx-name {
  display: flex;
  min-width: 0;
  white-space: nowrap;
}
.idx-head {
  overflow: hidden;
  text-overflow: ellipsis;
}
.idx-tail {
  flex: none;
}
.idx i {
  flex: none;
  font-style: normal;
  font-size: var(--text-facet-count);
  color: var(--soft);
}
.rail-foot {
  padding: 10px 16px 6px;
  border-top: 1px solid var(--line2);
  color: var(--soft);
  font-size: var(--text-sm);
}
.rail .load-error {
  margin: 4px 16px 10px;
}
</style>

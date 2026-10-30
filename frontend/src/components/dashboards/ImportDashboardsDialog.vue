<script setup lang="ts">
/**
 * Import a dashboard file (issue 440, S7): pick an NDJSON file, keep its IDs or make copies with
 * new ones, then read a result for each line. The file goes to the backend as it is, and the
 * backend checks every line. A line that gets "ID exists" made nothing. A failure can stop the
 * import after some lines made their dashboards, so the list reloads after every answer.
 */
import { computed, ref } from 'vue'

import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import UiSegControl from '@/components/ui/UiSegControl.vue'
import {
  EMPTY_FILE_NOTE,
  importDashboards,
  importFailureCopy,
  lineResultCopy,
  type ImportOutcome,
} from '@/dashboards/files'
import { logger } from '@/lib/logger'

const emit = defineEmits<{ close: []; imported: [created: number] }>()

const MODE_OPTS = [
  { value: 'keep', label: 'Keep the IDs' },
  { value: 'copy', label: 'Make copies' },
] as const

const picker = ref<HTMLInputElement | null>(null)
const file = ref<File | null>(null)
const mode = ref<'keep' | 'copy'>('keep')
const busy = ref(false)
const failure = ref<string | null>(null)
const outcome = ref<ImportOutcome | null>(null)

function sizeWords(bytes: number): string {
  if (bytes === 1) return '1 byte'
  return bytes < 1024 ? `${bytes} bytes` : `${Math.round(bytes / 1024).toLocaleString('en-US')} KB`
}

const fileLine = computed(() => (file.value ? `${file.value.name} · ${sizeWords(file.value.size)}` : 'No file chosen'))

function pick(e: Event) {
  file.value = (e.target as HTMLInputElement).files?.[0] ?? null
  failure.value = null
  outcome.value = null
}

async function run() {
  if (!file.value || busy.value) return
  if (file.value.size === 0) {
    failure.value = EMPTY_FILE_NOTE
    return
  }
  busy.value = true
  failure.value = null
  const copy = mode.value === 'copy'
  try {
    const answer = await importDashboards(file.value, copy)
    if (answer.ok) {
      outcome.value = answer.outcome
      logger.info('dashboards_imported', {
        created: answer.outcome.created,
        conflicts: answer.outcome.conflicts,
        invalid: answer.outcome.invalid,
      })
    } else {
      logger.warn('dashboards_import_failed', { status: answer.status })
      failure.value = importFailureCopy(answer.status, copy)
    }
    emit('imported', answer.ok ? answer.outcome.created : 0)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <ModalShell title="Import dashboards" subtitle="A file from Export: one dashboard on each line" :width="620" @close="emit('close')">
    <template v-if="!outcome">
      <UiField label="File" first>
        <div class="imp-file">
          <UiButton variant="control" @click="picker?.click()">Choose a file</UiButton>
          <span class="imp-name mono">{{ fileLine }}</span>
          <!-- eslint-disable-next-line vue/no-restricted-html-elements -- the file picker stays hidden; the Choose a file button opens it -->
          <input ref="picker" class="imp-input" type="file" accept=".ndjson,application/x-ndjson" @change="pick" />
        </div>
      </UiField>
      <UiField label="IDs" hint="a copy gets a new ID; an ID that exists is not made again">
        <UiSegControl v-model="mode" :options="MODE_OPTS" label="IDs" />
      </UiField>
      <p class="imp-note">You become the owner of each dashboard that the import makes.</p>
      <p v-if="failure" class="load-error" role="alert">{{ failure }}</p>
    </template>

    <template v-else>
      <p class="imp-sum" role="status">
        <b>{{ outcome.created }}</b> made · <b>{{ outcome.conflicts }}</b> with an ID that exists ·
        <b>{{ outcome.invalid }}</b> not correct
      </p>
      <div class="imp-results">
        <table class="tbl tbl-dense">
          <thead>
            <tr><th>Line</th><th>Result</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in outcome.results" :key="r.line" :data-status="r.status">
              <td class="mono">{{ r.line }}</td>
              <td>{{ lineResultCopy(r) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>

    <template #actions>
      <template v-if="!outcome">
        <UiButton variant="ghost" @click="emit('close')">Cancel</UiButton>
        <UiButton variant="primary" :disabled="!file || busy" @click="run">
          {{ busy ? 'Importing…' : 'Import' }}
        </UiButton>
      </template>
      <UiButton v-else variant="primary" @click="emit('close')">Done</UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.imp-file {
  display: flex;
  align-items: center;
  gap: 10px;
}
.imp-name {
  font-size: var(--text-mono-cell);
  color: var(--soft);
}
/* the native control has no kit skin; the kit button opens it */
.imp-input {
  display: none;
}
.imp-note {
  margin: 14px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.imp-sum {
  margin: 0 0 10px;
}
/* at most 1,000 lines: the list scrolls in its own viewport (DESIGN.md §2, no unbounded panels) */
.imp-results {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--line);
  border-radius: var(--r-sm);
}
.imp-results thead th {
  position: sticky;
  top: 0;
}
</style>

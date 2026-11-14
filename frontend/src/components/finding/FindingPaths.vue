<script setup lang="ts">
/**
 * The files of the findings of one row (issue 1077), under the row that opens it: one block
 * for each finding, in scanner order, never joined. A path comes from the content of a scanned
 * image, so it renders as text only. The finding page and the image page both use it.
 */
import { computed } from 'vue'

import { type FindingPaths, foundText, keptText, scannerName, shortDigest } from '@/findings/paths'

const props = defineProps<{
  entries: FindingPaths[]
  packageName: string
  version: string | null
}>()

/* a row that holds two digests of one tag says which digest each block is for */
const manyDigests = computed(() => new Set(props.entries.map((e) => e.digest)).size > 1)
</script>

<template>
  <div class="paths-panel">
    <section
      v-for="(e, i) in entries"
      :key="`${e.scanner}|${e.digest ?? i}`"
      class="paths-block"
      :aria-label="`Paths from ${scannerName(e.scanner)}`"
    >
      <p class="paths-say">
        {{ foundText(e, packageName, version) }}
        <span v-if="manyDigests && e.digest" class="paths-digest">Digest {{ shortDigest(e.digest) }}.</span>
      </p>
      <ul v-if="e.paths.length" class="paths-list">
        <li v-for="p in e.paths" :key="p">{{ p }}</li>
      </ul>
      <p v-if="keptText(e)" class="paths-say">{{ keptText(e) }}</p>
    </section>
  </div>
</template>

<style scoped>
.paths-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 14px 12px;
  background: var(--panel);
}
.paths-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.paths-say {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
.paths-digest {
  font-family: var(--font-mono);
}
.paths-list {
  margin: 0;
  padding-left: 18px;
  font-family: var(--font-mono);
  font-size: var(--text-mono-cell);
  color: var(--ink);
  line-height: 1.6;
}
/* a path is one long word: it breaks anywhere instead of pushing the table wider */
.paths-list li {
  overflow-wrap: anywhere;
}
</style>

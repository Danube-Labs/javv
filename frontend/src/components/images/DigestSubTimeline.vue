<script setup lang="ts">
/** Per-digest build history (M9c slice 3; SCREENS §8) — ONE scanner's committed scan-events
 * rendered as digest eras: a boundary is a BUILD CHANGE (marked, never a silent gap), a
 * `scan_order` jump is a missed-cycles gap, and a T before the first committed event renders
 * "not yet scanned then". Latest era first. */
import { computed } from 'vue'

import { digestEras, notYetScannedAt, type TimelineEvent } from '@/images/subTimeline'
import { fmt } from '@/lib/format'
import { lastDataAt } from '@/system/freshness'

const props = defineProps<{
  events: TimelineEvent[]
  scanner: string
  t: string | null
  currentDigest: string
}>()

const notYet = computed(() => notYetScannedAt(props.events, props.scanner, props.t))
const eras = computed(() => digestEras(props.events, props.scanner).reverse())
const short = (digest: string) => digest.replace(/^sha256:/, '').slice(0, 12)
</script>

<template>
  <div class="subtl">
    <p v-if="notYet" class="subtl-empty">
      Not yet scanned then: the first scan of this tag by {{ scanner }} is after this time.
    </p>
    <p v-else-if="eras.length === 0" class="subtl-empty">
      {{ scanner }} has no scan of this tag yet.
    </p>
    <ol v-else class="subtl-list">
      <template v-for="(era, i) in eras" :key="`${era.digest}-${era.firstAt}`">
        <li class="subtl-era" :class="{ 'subtl-on': era.digest === currentDigest && i === 0 }">
          <span class="subtl-dot" aria-hidden="true" />
          <div class="subtl-body">
            <span class="subtl-digest mono-cell" :title="era.digest">{{ short(era.digest) }}</span>
            <span v-if="era.digest === currentDigest" class="subtl-badge">this digest</span>
            <span class="subtl-meta">
              {{ lastDataAt(era.firstAt) }}<template v-if="era.lastAt !== era.firstAt"> → {{ lastDataAt(era.lastAt) }}</template>
              · {{ era.runs }} scan{{ era.runs === 1 ? '' : 's' }} · {{ fmt(era.totalAtLast) }} findings at last scan
            </span>
          </div>
        </li>
        <li v-if="i < eras.length - 1" class="subtl-marker" aria-hidden="false">
          {{ eras[i + 1]!.digest !== era.digest ? 'image build changed' : '' }}<template
            v-if="era.gapBefore"
          ><template v-if="eras[i + 1]!.digest !== era.digest"> · </template>missed scan cycles</template>
        </li>
      </template>
    </ol>
  </div>
</template>

<style scoped>
.subtl-empty {
  margin: 0;
  font-size: var(--text-body);
  color: var(--soft);
}
.subtl-list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 260px;
  overflow-y: auto;
}
.subtl-era {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 6px 0;
}
.subtl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--muted);
  margin-top: 5px;
  flex: none;
}
.subtl-on .subtl-dot {
  background: var(--teal);
}
.subtl-body {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
}
.subtl-digest {
  font-weight: 600;
  color: var(--ink);
}
.subtl-badge {
  font-family: var(--font-mono);
  font-size: var(--text-chip-sm);
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--coral-text);
  border: 1px solid var(--fpill-line);
  padding: 1px 6px;
  border-radius: 999px;
}
.subtl-meta {
  width: 100%;
  font-size: var(--text-sm);
  color: var(--soft);
  font-family: var(--font-mono);
}
.subtl-marker {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--soft);
  padding: 2px 0 2px 18px;
  border-left: 2px dashed var(--line);
  margin-left: 3px;
}
</style>

<script setup lang="ts">
/**
 * A thin bar on the bottom edge of its positioned parent that tells the user the app is working
 * (issue 902, operator decision D1 B). It shows only after SHOW_AFTER_MS of work, because a bar
 * that flashes on a fast click makes the app look broken. While it shows it grows, more slowly
 * near the end; when the work ends it fills, then fades.
 *
 * The parent owns what `busy` means: the app shell passes the page changes and API requests.
 */
import { onUnmounted, ref, watch } from 'vue'

const props = defineProps<{ busy: boolean }>()

/** Kibana waits 250 ms, Nuxt 200 ms, GitHub 500 ms before its bar shows. */
const SHOW_AFTER_MS = 250
/** Work that ends and starts again inside this gap (a page change, then its first requests)
 * keeps one bar instead of two. */
const DONE_AFTER_MS = 150
const START = 0.08
const NEAR_END = 0.9
/** The growth slows on this time scale: about 63% of the way to NEAR_END after 1.2 s. */
const GROW_SCALE_MS = 1200
const TICK_MS = 100
/** After the fade (--dur-quick delay + --dur-panel), out of sight, the bar goes back to empty. */
const RESET_AFTER_MS = 400

const shown = ref(false)
const progress = ref(0)
let showTimer: ReturnType<typeof setTimeout> | undefined
let doneTimer: ReturnType<typeof setTimeout> | undefined
let tick: ReturnType<typeof setInterval> | undefined
let resetTimer: ReturnType<typeof setTimeout> | undefined

function stopGrowing() {
  clearInterval(tick)
  tick = undefined
}

function show() {
  const started = Date.now()
  clearTimeout(resetTimer)
  shown.value = true
  progress.value = START
  stopGrowing()
  tick = setInterval(() => {
    const t = (Date.now() - started) / GROW_SCALE_MS
    progress.value = START + (NEAR_END - START) * (1 - Math.exp(-t))
  }, TICK_MS)
}

function done() {
  stopGrowing()
  progress.value = 1
  shown.value = false
  resetTimer = setTimeout(() => (progress.value = 0), RESET_AFTER_MS)
}

watch(
  () => props.busy,
  (busy) => {
    if (busy) {
      clearTimeout(doneTimer)
      if (!shown.value) showTimer ??= setTimeout(() => ((showTimer = undefined), show()), SHOW_AFTER_MS)
    } else {
      clearTimeout(showTimer)
      showTimer = undefined
      if (shown.value) doneTimer = setTimeout(done, DONE_AFTER_MS)
    }
  },
  { immediate: true },
)

onUnmounted(() => {
  clearTimeout(showTimer)
  clearTimeout(doneTimer)
  clearTimeout(resetTimer)
  stopGrowing()
})
</script>

<template>
  <div
    class="ui-lb"
    :class="{ 'ui-lb-on': shown }"
    role="progressbar"
    aria-label="Loading"
    :aria-hidden="shown ? undefined : 'true'"
  >
    <div class="ui-lb-fill" :style="{ transform: `scaleX(${progress})` }" />
  </div>
</template>

<style scoped>
.ui-lb {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -1px;
  height: 2px;
  overflow: hidden;
  pointer-events: none;
  opacity: 0;
  transition: opacity var(--dur-panel) var(--ease-out) var(--dur-quick);
}
.ui-lb-on {
  opacity: 1;
  transition-delay: 0s;
}
.ui-lb-fill {
  height: 100%;
  background: var(--coral);
  transform-origin: left;
  transition: transform var(--dur-panel) var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .ui-lb,
  .ui-lb-fill {
    transition: none;
  }
}
</style>

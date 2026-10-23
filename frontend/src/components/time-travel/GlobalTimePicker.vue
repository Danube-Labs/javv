<script setup lang="ts">
/**
 * POC (operator option D, 2026-07-09): ONE time-RANGE control replacing the
 * two-section time-travel/trend-window menu. A range maps exactly onto the shipped backend:
 * the END of the range is the whole-app `as_of` T (D28 — `null` when the range ends now), the
 * SPAN is `days` for the M9c trend charts (int 1–365). One mental model, accurate copy:
 * tables show state at the END of the range; charts aggregate the whole span.
 * The button goes amber (`--hist-*`) whenever the range ends in the past.
 */
import { computed, ref } from 'vue'

import AppIcon from '@/components/ui/AppIcon.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiDropdown from '@/components/ui/UiDropdown.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'

const timeTravel = useTimeTravelStore()
const open = ref(false)
const relN = ref(30)
const relUnit = ref<'minutes' | 'hours' | 'days' | 'weeks'>('days')
const fromDate = ref('')
const fromTime = ref('00:00')
const toDate = ref('')
const toTime = ref('')

const UNIT_MS = { minutes: 60_000, hours: 3_600_000, days: 86_400_000, weeks: 604_800_000 } as const
const TIME_RE = /^([01]?\d|2[0-3]):[0-5]\d$/ // strict 24h HH:mm — no AM/PM anywhere

/* quick ranges, all ending now — the trends contract is whole days 1..365 */
const PRESETS: readonly [string, number][] = [
  ['Last 24 hours', 1],
  ['Last 7 days', 7],
  ['Last 30 days', 30],
  ['Last 90 days', 90],
  ['Last 180 days', 180],
  ['Last 1 year', 365],
]

const DAY_MS = 86_400_000

/* 24-hour display everywhere — never AM/PM */
const fmtD = (d: Date) =>
  d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

// Rewound, the chip names the T being viewed — derived from `t` ITSELF (local rendering),
// never from picker state: a URL-borne `t` (pasted link, hand-edited) sets no windowLabel,
// and the URL's ISO is UTC while every on-screen date is local — without this the screen
// shows rows stamped "after" a T the user believes they picked (operator bug, 2026-07-12).
const buttonLabel = computed(() =>
  timeTravel.isNow || timeTravel.t === null
    ? timeTravel.windowLabel
    : `At ${fmtD(new Date(timeTravel.t))}`,
)
// hover answers "which exact instant?" in the URL's own frame — the local↔UTC bridge. At now
// it carries the range in full: a long custom range truncates on one line (issue 647).
const buttonTitle = computed(() =>
  timeTravel.t === null ? timeTravel.windowLabel : `Viewing state at ${timeTravel.t} (UTC)`,
)

function applyPreset(label: string, days: number) {
  timeTravel.backToNow()
  timeTravel.setWindow(days, label)
  open.value = false
}

function applyRelative() {
  if (!relN.value || relN.value < 1) return
  // the store keeps the TRUE (possibly sub-day) span; query builders ceil+clamp to the
  // day-grained 1..365 contract at emission — pre-clamping here killed isSubDayWindow (audit 343)
  const days = Math.min(365, (relN.value * UNIT_MS[relUnit.value]) / DAY_MS)
  const unit = relUnit.value.slice(0, -1)
  timeTravel.backToNow()
  timeTravel.setWindow(days, `Last ${relN.value} ${unit}${relN.value === 1 ? '' : 's'}`)
  open.value = false
}

const parseSide = (date: string, time: string): Date | null => {
  if (!date || !TIME_RE.test(time)) return null
  return new Date(`${date}T${time.padStart(5, '0')}:00`)
}

/* the last day a range can end on is the local today: a later time today reads as now (see
 * applyCustom), but a later day put dates on the button and the captions that the charts did not
 * show, since they end now (issue 984) */
const pad2 = (n: number) => String(n).padStart(2, '0')
const today = () => {
  const d = new Date()
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`
}

const customValid = computed(() => {
  const from = parseSide(fromDate.value, fromTime.value)
  const to = parseSide(toDate.value, toTime.value)
  return from !== null && to !== null && from.getTime() < to.getTime() && toDate.value <= today()
})

function applyCustom() {
  const from = parseSide(fromDate.value, fromTime.value)
  const to = parseSide(toDate.value, toTime.value)
  if (!from || !to || !customValid.value) return
  // charts take whole days (trends contract int 1..365); the END is minute-precise as_of
  const span = Math.min(365, Math.max(1, Math.round((to.getTime() - from.getTime()) / DAY_MS) || 1))
  const label = `${fmtD(from)} → ${fmtD(to)}`
  if (to.getTime() >= Date.now() - 60_000) {
    timeTravel.backToNow() // range ends now-ish: tables show current state
  } else {
    timeTravel.rewindTo(to.toISOString()) // past end: tables show as-scanned at that minute
  }
  timeTravel.setWindow(span, label)
  open.value = false
}

function backToNow() {
  timeTravel.backToNow()
  timeTravel.setWindow(30, 'Last 30 days')
  open.value = false
}

</script>

<template>
  <UiDropdown v-model:open="open">
    <template #trigger="{ toggle }">
      <button
        class="time-range"
        :class="{ 'time-range-hist': !timeTravel.isNow }"
        aria-label="Time range"
        :title="buttonTitle"
        @click="toggle"
      >
        <AppIcon :name="timeTravel.isNow ? 'calendar' : 'rewind'" :size="14" />
        <span class="time-range-label">{{ buttonLabel }}</span>
        <AppIcon name="chevron" :size="13" />
      </button>
    </template>

    <div class="dd-menu time-menu">
      <div class="tt-note">
        One range drives the whole app: <b>tables show state at the end of the range</b> (a past
        end = as-scanned history) · charts aggregate the span.
      </div>

      <div class="dd-head">Quick select</div>
      <div class="time-rel">
        <span class="time-rel-label">Last</span>
        <input
          v-model.number="relN"
          class="num-input mono-cell"
          type="number"
          min="1"
          max="365"
          aria-label="Range length"
        />
        <select v-model="relUnit" class="select-input" aria-label="Range unit">
          <option value="minutes">minutes</option>
          <option value="hours">hours</option>
          <option value="days">days</option>
          <option value="weeks">weeks</option>
        </select>
        <UiButton variant="quiet" class="time-apply" @click="applyRelative">Apply</UiButton>
      </div>

      <div class="dd-head">Commonly used</div>
      <div class="time-presets">
        <button
          v-for="[p, days] in PRESETS"
          :key="p"
          class="time-preset"
          :class="{ 'time-preset-on': timeTravel.isNow && timeTravel.windowLabel === p }"
          @click="applyPreset(p, days)"
        >
          {{ p }}
        </button>
      </div>

      <div class="dd-head">Absolute range (24h)</div>
      <div class="time-abs">
        <input v-model="fromDate" class="text-input mono-cell" type="date" :max="today()" aria-label="Range start date" />
        <input
          v-model="fromTime"
          class="text-input mono-cell hhmm"
          type="text"
          placeholder="HH:mm"
          maxlength="5"
          aria-label="Range start time (24h)"
        />
        <span class="time-arrow">→</span>
        <input v-model="toDate" class="text-input mono-cell" type="date" :max="today()" aria-label="Range end date" />
        <input
          v-model="toTime"
          class="text-input mono-cell hhmm"
          type="text"
          placeholder="HH:mm"
          maxlength="5"
          aria-label="Range end time (24h)"
        />
        <UiButton variant="quiet" class="time-apply" :disabled="!customValid" @click="applyCustom">Apply</UiButton>
      </div>

      <button v-if="!timeTravel.isNow" class="back-now" @click="backToNow">
        <AppIcon name="rewind" :size="13" /> Back to now (Last 30 days)
      </button>
    </div>
  </UiDropdown>
</template>

<style scoped>
.time-range {
  display: flex;
  flex: none;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
  /* topbar control register (operator, 2026-07-17): same 40px height as the cluster switcher */
  height: 40px;
  border: 2px solid var(--line); /* topbar register: 2px per the keep-beige ruling */
  border-radius: 10px;
  padding: 0 12px;
  color: var(--ink); /* primary control text — never washy soft-on-panel */
  font-size: var(--text-dd-item);
  background: var(--panel);
  font-family: var(--font-ui);
  cursor: default;
}
/* one line always (issue 647); only a long custom range reaches the cap, and its full text is
   in the button's title */
.time-range-label {
  max-width: 30ch;
  overflow: hidden;
  text-overflow: ellipsis;
}
.time-range svg {
  flex: none;
}
.time-range:hover {
  background: var(--control-hover-bg); /* wash + border — border-only hover is invisible */
  border-color: var(--control-hover-line);
}
.time-range:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
.time-range-hist {
  background: var(--hist-bg);
  border-color: var(--hist-line);
  color: var(--hist-fg);
}
.dd-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 30;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 10px;
  box-shadow: var(--dd-shadow);
  padding: 6px;
}
.time-menu {
  min-width: 340px;
}
.dd-head {
  font-family: var(--font-mono);
  font-size: var(--text-dd-head);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--soft);
  padding: 8px 12px 6px;
}
.tt-note {
  font-size: var(--text-sm);
  color: var(--ink);
  padding: 8px 10px;
  line-height: 1.5;
  border-bottom: 1px solid var(--line2);
  margin-bottom: 4px;
}
.time-rel {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 10px;
}
.time-rel-label {
  font-size: var(--text-control);
  color: var(--ink);
}
.time-apply {
  margin-left: auto;
}
.time-presets {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 3px;
  padding: 2px 8px 10px;
}
.time-preset {
  border: 0;
  background: transparent;
  text-align: left;
  padding: 6px 9px;
  border-radius: 7px;
  font-size: var(--text-control);
  color: var(--ink);
  cursor: default;
}
.time-preset:hover {
  background: var(--panel);
}
.time-preset-on {
  background: var(--dd-on-bg);
  color: var(--coral-text);
  font-weight: 600;
}
.time-abs {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 4px 10px 8px;
}
.time-arrow {
  color: var(--soft);
  flex: none;
}
.text-input,
.num-input {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: var(--text-sm);
  color: var(--ink);
  background: var(--card);
  outline: none;
  font-family: inherit;
}
.num-input {
  width: 64px;
}
.hhmm {
  width: 62px;
  text-align: center;
}
.text-input:focus,
.num-input:focus {
  border-color: var(--coral);
}
.select-input {
  border: 1px solid var(--line);
  background: var(--card);
  border-radius: 8px;
  padding: 6px 8px;
  font-size: var(--text-control);
  color: var(--ink);
  outline: none;
  width: 96px;
}
.select-input:focus {
  border-color: var(--coral);
}
.mono-cell {
  font-family: var(--font-mono);
}
.back-now {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  border: 0;
  border-top: 1px solid var(--line2);
  background: transparent;
  color: var(--coral-text);
  font-size: var(--text-control);
  font-weight: 600;
  padding: 9px 10px 7px;
  margin-top: 4px;
  cursor: default;
}
.back-now:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 1px;
}
</style>

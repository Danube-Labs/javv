/**
 * Pins the range-control semantics (#300/#301): range END → global as_of (minute-precise,
 * null when ending now), range SPAN → whole-day windowDays (sub-day quick-selects round UP),
 * strict 24h HH:mm validation, 24-hour labels — never AM/PM. A range ends today at the latest:
 * a later day labelled dates that the charts did not show (issue 984).
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import GlobalTimePicker from '@/components/time-travel/GlobalTimePicker.vue'
import { useTimeTravelStore } from '@/stores/timeTravel'

async function open(w: ReturnType<typeof mount>) {
  await w.find('.time-range').trigger('click')
}

describe('GlobalTimePicker (single range control)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useRealTimers()
  })

  it('quick select keeps the TRUE sub-day span — builders clamp at emission (audit 343)', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    await open(w)
    await w.find('input[aria-label="Range length"]').setValue(90)
    await w.find('select[aria-label="Range unit"]').setValue('minutes')
    await w.find('.time-rel .time-apply').trigger('click')
    expect(store.windowDays).toBeCloseTo(0.0625) // isSubDayWindow drives the sub-day notes
    expect(store.windowLabel).toBe('Last 90 minutes')
    expect(store.t).toBeNull() // quick selects end now — no as_of
  })

  it('weeks multiply into days; presets set span and end-now', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    await open(w)
    await w.find('input[aria-label="Range length"]').setValue(2)
    await w.find('select[aria-label="Range unit"]').setValue('weeks')
    await w.find('.time-rel .time-apply').trigger('click')
    expect(store.windowDays).toBe(14)

    await open(w)
    const preset = w.findAll('.time-preset').find((b) => b.text() === 'Last 90 days')
    await preset?.trigger('click')
    expect(store.windowDays).toBe(90)
    expect(store.windowLabel).toBe('Last 90 days')
    expect(store.t).toBeNull()
  })

  it('an absolute range ending in the past sets minute-precise as_of + the day span', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    await open(w)
    await w.find('input[aria-label="Range start date"]').setValue('2026-07-01')
    await w.find('input[aria-label="Range start time (24h)"]').setValue('08:00')
    await w.find('input[aria-label="Range end date"]').setValue('2026-07-08')
    await w.find('input[aria-label="Range end time (24h)"]').setValue('14:30')
    await w.find('.time-abs .time-apply').trigger('click')
    expect(store.t).toBe(new Date('2026-07-08T14:30:00').toISOString())
    expect(store.windowDays).toBe(7)
    expect(store.windowLabel).not.toMatch(/AM|PM/i) // 24h labels, never AM/PM
    expect(store.windowLabel).toContain('14:30')
  })

  it('an absolute range ending later today stays at T=now (no as_of)', async () => {
    // noon, so +1h is still today: a later day is refused (the describe below)
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 6, 10, 12, 0))
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    const future = new Date(Date.now() + 3_600_000) // +1h local
    const pad = (n: number) => String(n).padStart(2, '0')
    const d = `${future.getFullYear()}-${pad(future.getMonth() + 1)}-${pad(future.getDate())}`
    const hm = `${pad(future.getHours())}:${pad(future.getMinutes())}`
    await open(w)
    await w.find('input[aria-label="Range start date"]').setValue(d)
    await w.find('input[aria-label="Range start time (24h)"]').setValue('00:00')
    await w.find('input[aria-label="Range end date"]').setValue(d)
    await w.find('input[aria-label="Range end time (24h)"]').setValue(hm)
    await w.find('.time-abs .time-apply').trigger('click')
    expect(store.t).toBeNull() // ends ahead of now → current state, no as_of
    expect(store.windowLabel).toMatch(/→/) // applied: the custom range label
    expect(store.windowLabel).not.toMatch(/AM|PM/i)
  })

  it('rejects invalid 24h times — Apply stays disabled', async () => {
    const w = mount(GlobalTimePicker)
    await open(w)
    await w.find('input[aria-label="Range start date"]').setValue('2026-07-01')
    await w.find('input[aria-label="Range start time (24h)"]').setValue('25:00') // invalid hour
    await w.find('input[aria-label="Range end date"]').setValue('2026-07-02')
    await w.find('input[aria-label="Range end time (24h)"]').setValue('9:75') // invalid minutes
    expect((w.find('.time-abs .time-apply').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('rewound, the chip names T from `t` itself — a URL-borne rewind can never hide its instant', async () => {
    // operator bug 2026-07-12: a pasted ?t=…Z URL sets no windowLabel, so the chip read
    // "Last 30 days" while the app was rewound — and the URL's UTC frame beside local
    // on-screen dates made a correct SLA look like a reset
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    store.rewindTo('2026-07-08T23:59:59.999Z') // as ttFromQuery would — no setWindow call
    await w.vm.$nextTick()
    const chip = w.find('.time-range')
    const local = new Date('2026-07-08T23:59:59.999Z').toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
    expect(chip.text()).toContain(`At ${local}`) // derived from t, not picker state
    expect(chip.attributes('title')).toContain('2026-07-08T23:59:59.999Z')
    expect(chip.attributes('title')).toContain('UTC') // the local↔UTC bridge on hover
  })

  it('at T=now the chip keeps the window label, and its title carries it in full', async () => {
    // issue 647: a long custom range truncates on one line, so the title is where it stays whole
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    const chip = w.find('.time-range')
    expect(chip.find('.time-range-label').text()).toBe('Last 30 days')
    expect(chip.attributes('title')).toBe('Last 30 days')
    store.setWindow(1, 'Sep 29, 13:26 → Oct 1, 23:59')
    await w.vm.$nextTick()
    expect(chip.find('.time-range-label').text()).toBe('Sep 29, 13:26 → Oct 1, 23:59')
    expect(chip.attributes('title')).toBe('Sep 29, 13:26 → Oct 1, 23:59')
  })

  it('back-to-now clears as_of and restores the default window', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    store.rewindTo('2026-07-08T14:30:00.000Z')
    store.setWindow(7, 'Jul 1, 08:00 → Jul 8, 14:30')
    await open(w)
    await w.find('.back-now').trigger('click')
    expect(store.t).toBeNull()
    expect(store.windowDays).toBe(30)
    expect(store.windowLabel).toBe('Last 30 days')
  })
})

describe('a range that ends after today (issue 984)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 23, 18, 0)) // 23 October, local
  })
  afterEach(() => vi.useRealTimers())

  async function pick(w: ReturnType<typeof mount>, fromDay: string, toDay: string) {
    await open(w)
    await w.find('input[aria-label="Range start date"]').setValue(fromDay)
    await w.find('input[aria-label="Range start time (24h)"]').setValue('00:00')
    await w.find('input[aria-label="Range end date"]').setValue(toDay)
    await w.find('input[aria-label="Range end time (24h)"]').setValue('00:00')
  }
  const apply = (w: ReturnType<typeof mount>) => w.find('.time-abs .time-apply')

  it('the date fields end at today', async () => {
    const w = mount(GlobalTimePicker)
    await open(w)
    for (const label of ['Range start date', 'Range end date'])
      expect(w.find(`input[aria-label="${label}"]`).attributes('max')).toBe('2026-10-23')
  })

  it('an end after today keeps Apply disabled, and nothing changes', async () => {
    const w = mount(GlobalTimePicker)
    const store = useTimeTravelStore()
    await pick(w, '2026-10-30', '2026-11-06')
    expect((apply(w).element as HTMLButtonElement).disabled).toBe(true)
    await apply(w).trigger('click')
    expect(store.windowLabel).toBe('Last 30 days')
  })

  it('a range that ends today applies', async () => {
    const w = mount(GlobalTimePicker)
    await pick(w, '2026-10-16', '2026-10-23')
    expect((apply(w).element as HTMLButtonElement).disabled).toBe(false)
  })
})

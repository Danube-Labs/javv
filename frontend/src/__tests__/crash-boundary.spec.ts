/**
 * A page that fails while it is drawn is replaced by the error page; an error in a handler is
 * logged and the page stays (issue 675). Vue names the failing phase differently in dev and in a
 * production build, so the rule is pinned for both spellings.
 */
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, reactive, ref } from 'vue'

import CrashBoundary from '@/components/system/CrashBoundary.vue'
import { logger } from '@/lib/logger'
import { errorMessage, errorStack, logUnhandledRejections, pageCrashed, replacesPage } from '@/system/crash'

const route = reactive({ path: '/findings', fullPath: '/findings' })
const push = vi.fn<(to: unknown) => void>()
vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRoute: () => route,
  useRouter: () => ({ push }),
}))

describe('replacesPage', () => {
  it.each(['setup function', 'render function', 'component update', 'beforeMount hook'])(
    'a failed draw replaces the page: %s',
    (info) => expect(replacesPage(info)).toBe(true),
  )

  it.each(['0', '1', '15', 'bm'])('the same phases as production codes: %s', (code) => {
    expect(replacesPage(`https://vuejs.org/error-reference/#runtime-${code}`)).toBe(true)
  })

  it.each([
    'native event handler',
    'component event handler',
    'watcher callback',
    'mounted hook',
    'https://vuejs.org/error-reference/#runtime-5',
    'https://vuejs.org/error-reference/#runtime-3',
    'https://vuejs.org/error-reference/#runtime-m',
    '',
  ])('anything else leaves the page alone: %s', (info) => expect(replacesPage(info)).toBe(false))
})

describe('errorMessage', () => {
  it('reads an Error and stringifies anything else', () => {
    expect(errorMessage(new Error('boom'))).toBe('boom')
    expect(errorMessage('plain')).toBe('plain')
    expect(errorMessage(undefined)).toBe('undefined')
  })
})

describe('errorStack (issue 749)', () => {
  const thrown = (stack: string) => Object.assign(new TypeError('boom'), { stack })
  const CHROMIUM = [
    "TypeError: Cannot read properties of undefined (reading 'series')",
    '    at https://javv.example/assets/OverviewView-AbC12.js:1:2345',
    '    at async Promise.all (index 0)',
    '    at f (https://javv.example/assets/index-Xy9.js:2:10)',
  ].join('\n')

  it("keeps the frames, without the message line or the page's own origin", () => {
    expect(errorStack(thrown(CHROMIUM), 'https://javv.example')).toEqual([
      'at /assets/OverviewView-AbC12.js:1:2345',
      'at async Promise.all (index 0)',
      'at f (/assets/index-Xy9.js:2:10)',
    ])
  })

  it('reads Firefox and Safari stacks, which list frames only', () => {
    const stack = 'load@https://javv.example/assets/a.js:1:2\n@https://javv.example/assets/b.js:3:4\n'
    expect(errorStack(thrown(stack), 'https://javv.example')).toEqual(['load@/assets/a.js:1:2', '@/assets/b.js:3:4'])
  })

  it('keeps at most five frames', () => {
    const stack = ['TypeError: boom', ...Array.from({ length: 9 }, (_, i) => `    at f${i} (x.js:${i}:1)`)].join('\n')
    expect(errorStack(thrown(stack), '')).toEqual([0, 1, 2, 3, 4].map((i) => `at f${i} (x.js:${i}:1)`))
  })

  it('gives nothing for a value that is not an Error', () => {
    expect(errorStack('plain', 'https://javv.example')).toEqual([])
    expect(errorStack(undefined)).toEqual([])
    expect(errorStack({ stack: CHROMIUM })).toEqual([])
  })
})

describe('logUnhandledRejections (issue 749)', () => {
  it('logs a rejection nothing caught as an app error, with where it threw', () => {
    // the same spy the boundary tests below share, so it is cleared, never restored
    const logged = vi.spyOn(logger, 'error').mockImplementation(() => {})
    logged.mockClear()
    const target = new EventTarget()
    logUnhandledRejections(target, () => '/overview')
    const reason = new TypeError("Cannot read properties of undefined (reading 'facets')")
    target.dispatchEvent(Object.assign(new Event('unhandledrejection'), { reason }))
    expect(logged).toHaveBeenCalledWith('app error', {
      route: '/overview',
      info: 'unhandled rejection',
      message: "Cannot read properties of undefined (reading 'facets')",
      stack: errorStack(reason),
    })
    expect(errorStack(reason).length).toBeGreaterThan(0)
    // a console preview shows five keys and the logger puts timestamp, level and event first, so
    // the message must be one of the first two fields
    expect(Object.keys(logged.mock.calls[0]![1] as object).slice(0, 2)).toContain('message')
  })
})

// the crash flag is shared, so a boundary left mounted would redraw its broken page into the next test
enableAutoUnmount(afterEach)

describe('CrashBoundary', () => {
  const logged = vi.spyOn(logger, 'error').mockImplementation(() => {})
  const broken = ref(true)
  const ThrowsInSetup = defineComponent({
    setup() {
      if (broken.value) throw new Error('setup broke')
      return () => h('p', { class: 'page' }, 'the page')
    },
  })
  const ThrowsInRender = defineComponent({
    props: { fail: Boolean },
    render() {
      if (this.fail) throw new Error('render broke')
      return h('p', { class: 'page' }, 'the page')
    },
  })
  const ThrowsOnClick = defineComponent({
    render: () =>
      h('button', {
        class: 'page',
        onClick: () => {
          throw new Error('click broke')
        },
      }),
  })
  const inBoundary = (child: () => unknown) => mount(CrashBoundary, { slots: { default: child } })

  beforeEach(() => {
    pageCrashed.value = false
    broken.value = true
    route.path = route.fullPath = '/findings'
    logged.mockClear()
    push.mockClear()
  })
  afterEach(() => {
    pageCrashed.value = false
  })

  it('shows the page when nothing fails', () => {
    broken.value = false
    const w = inBoundary(() => h(ThrowsInSetup))
    expect(w.get('.page').text()).toBe('the page')
    expect(w.find('h1').exists()).toBe(false)
    expect(logged).not.toHaveBeenCalled()
  })

  it('replaces a page that throws while it is set up, and logs it', async () => {
    const w = inBoundary(() => h(ThrowsInSetup))
    await nextTick()
    expect(w.get('h1').text()).toBe('JAVV cannot show this page')
    expect(w.find('.page').exists()).toBe(false)
    expect(logged).toHaveBeenCalledWith('page crashed', {
      route: '/findings',
      info: 'setup function',
      message: 'setup broke',
      stack: expect.any(Array),
    })
  })

  it('replaces a page that throws on a later redraw', async () => {
    const fail = ref(false)
    const w = inBoundary(() => h(ThrowsInRender, { fail: fail.value }))
    expect(w.find('.page').exists()).toBe(true)
    fail.value = true
    await nextTick()
    await nextTick()
    expect(w.get('h1').text()).toBe('JAVV cannot show this page')
    expect(logged.mock.calls[0]![0]).toBe('page crashed')
  })

  it('keeps the page when a click handler throws, and still logs it', async () => {
    const w = inBoundary(() => h(ThrowsOnClick))
    await w.get('button.page').trigger('click')
    expect(w.find('h1').exists()).toBe(false)
    expect(w.find('button.page').exists()).toBe(true)
    expect(logged).toHaveBeenCalledWith('page error', {
      route: '/findings',
      info: 'native event handler',
      message: 'click broke',
      stack: expect.any(Array),
    })
    // the same five-key preview: the message must be one of the first two fields
    expect(Object.keys(logged.mock.calls[0]![1] as object).slice(0, 2)).toContain('message')
  })

  it('"Try again" draws the page again', async () => {
    const w = inBoundary(() => h(ThrowsInSetup))
    await nextTick()
    broken.value = false
    await w.findAll('button').find((b) => b.text() === 'Try again')!.trigger('click')
    expect(w.get('.page').text()).toBe('the page')
  })

  it('"Try again" on a page that is still broken shows the error page again', async () => {
    const w = inBoundary(() => h(ThrowsInSetup))
    await nextTick()
    await w.findAll('button').find((b) => b.text() === 'Try again')!.trigger('click')
    await nextTick()
    expect(w.get('h1').text()).toBe('JAVV cannot show this page')
    expect(logged).toHaveBeenCalledTimes(2)
  })

  it('"Back to Overview" clears the error and navigates', async () => {
    const w = inBoundary(() => h(ThrowsInSetup))
    await nextTick()
    broken.value = false
    await w.findAll('button').find((b) => b.text() === 'Back to Overview')!.trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'overview' })
    expect(pageCrashed.value).toBe(false)
  })

  it('moving to another page clears the error', async () => {
    const w = inBoundary(() => h(ThrowsInSetup))
    await nextTick()
    broken.value = false
    route.path = route.fullPath = '/images'
    await nextTick()
    await nextTick()
    expect(w.get('.page').text()).toBe('the page')
  })

  it('shows the error page when a page file failed to load', async () => {
    broken.value = false
    const w = inBoundary(() => h(ThrowsInSetup))
    pageCrashed.value = true
    await nextTick()
    expect(w.get('h1').text()).toBe('JAVV cannot show this page')
  })
})

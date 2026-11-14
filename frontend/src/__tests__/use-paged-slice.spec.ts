/**
 * usePagedSlice: display pages over a row set that the client already holds, behind GridPager.
 */
import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'

import { usePagedSlice } from '@/composables/usePagedSlice'

const numbers = (n: number) => Array.from({ length: n }, (_, i) => i)

describe('usePagedSlice', () => {
  it('shows the rows of the page, and says when a next page exists', () => {
    const rows = ref(numbers(25))
    const { page, shown, hasNext } = usePagedSlice(() => rows.value)
    expect(shown.value).toEqual(numbers(10))
    expect(hasNext.value).toBe(true)
    page.value = 2
    expect(shown.value).toEqual([20, 21, 22, 23, 24])
    expect(hasNext.value).toBe(false)
  })

  it('starts at the size it is given', () => {
    const { size, shown } = usePagedSlice(() => numbers(30), 25)
    expect(size.value).toBe(25)
    expect(shown.value).toHaveLength(25)
  })

  it('a new size shows page 1 with that number of rows', () => {
    const { page, size, shown, setSize } = usePagedSlice(() => numbers(60))
    page.value = 3
    setSize(25)
    expect([page.value, size.value]).toEqual([0, 25])
    expect(shown.value).toEqual(numbers(25))
  })

  it('new rows show page 1', async () => {
    const rows = ref(numbers(30))
    const { page } = usePagedSlice(() => rows.value)
    page.value = 2
    rows.value = numbers(40)
    await nextTick()
    expect(page.value).toBe(0)
  })

  it('with keepPage, new rows keep the page', async () => {
    const rows = ref(numbers(30))
    const { page, shown } = usePagedSlice(() => rows.value, 10, { keepPage: true })
    page.value = 1
    rows.value = numbers(30).map((n) => n + 100)
    await nextTick()
    expect(page.value).toBe(1)
    expect(shown.value).toEqual(numbers(10).map((n) => n + 110))
  })

  it('with keepPage, a new size still shows page 1', () => {
    const { page, setSize } = usePagedSlice(() => numbers(60), 10, { keepPage: true })
    page.value = 2
    setSize(25)
    expect(page.value).toBe(0)
  })
})

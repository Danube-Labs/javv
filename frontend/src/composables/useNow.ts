import { onUnmounted, ref, type Ref } from 'vue'

/** The clock as a ref, re-read every `ms` while the component is mounted. A `computed` that
 * reads `Date.now()` alone never recomputes; one that reads this moves with it. */
export function useNow(ms: number): Ref<number> {
  const now = ref(Date.now())
  const timer = setInterval(() => {
    now.value = Date.now()
  }, ms)
  onUnmounted(() => clearInterval(timer))
  return now
}

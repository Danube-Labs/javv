/**
 * Each package and version of a CVE on one image, for the package menu of a finding's head band
 * (issue 1227). One read of the findings of the CVE on the image, at the limit of the read (500),
 * so the menu is never cut at the 10 rows of the evidence read. `cut` is true when the image has
 * more findings than that. A refused read gives no packages: the head band then shows the package
 * name alone.
 */
import { computed, ref, watch, type Ref } from 'vue'

import { closeUnpaged } from '@/api/cursors'
import { searchFindingsApiV1FindingsGet, type SearchFindingsApiV1FindingsGetData } from '@/api/generated'
import { useApi } from '@/composables/useApi'
import { packagesOnImage, type PackageOnImage } from '@/findings/detailViewModel'
import { logger } from '@/lib/logger'
import { useClusterStore } from '@/stores/cluster'
import type { FindingRow } from '@/stores/findings'

/** the `size` limit of GET /api/v1/findings */
const READ_LIMIT = 500

export function usePackagesOnImage(cveId: Ref<string>, digest: Ref<string | null>) {
  const clusterStore = useClusterStore()
  const { withGlobals } = useApi()
  const packages = ref<PackageOnImage[]>([])
  const cut = ref(false)
  const query = computed(() =>
    clusterStore.selectedId && cveId.value && digest.value
      ? withGlobals({ cve_id: [cveId.value], image_digest: digest.value, size: READ_LIMIT })
      : null,
  )
  let seq = 0
  watch(
    query,
    async (q, old) => {
      if (!q || JSON.stringify(q) === JSON.stringify(old)) return
      const mine = ++seq
      const response = await searchFindingsApiV1FindingsGet({
        query: q as SearchFindingsApiV1FindingsGetData['query'],
      })
      closeUnpaged(response.data?.next_cursor, !q.as_of) // one page only: never paged
      if (mine !== seq) return // a newer read owns the menu now
      if (response.response?.ok && response.data) {
        const body = response.data as { data: FindingRow[]; total: { value: number } }
        packages.value = packagesOnImage(body.data)
        cut.value = body.total.value > body.data.length
      } else {
        packages.value = []
        cut.value = false
        logger.warn('finding_packages_failed', { status: response.response?.status })
      }
    },
    { immediate: true },
  )
  return { packages, cut }
}

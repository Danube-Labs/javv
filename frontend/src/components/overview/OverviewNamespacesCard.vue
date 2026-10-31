<script setup lang="ts">
/**
 * The Overview "Per namespace" card (issue 384 split — extracted from OverviewView): the top
 * namespaces by findings under the scanner lens, each row a click-through to the
 * namespace-filtered grid. Per-namespace counts overlap by design (D30 — the all-namespaces
 * total is the only deduped number). Skinned by the shared base.css table (no scoped re-own).
 * Overview passes its facets read; on a dashboard the card reads its own (useFindingsFacets),
 * with the panel's filters in the read and the links.
 */
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import type { ViewPreset } from '@/api/generated'
import AppIcon from '@/components/ui/AppIcon.vue'
import RowLink from '@/components/ui/RowLink.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiSkeleton from '@/components/ui/UiSkeleton.vue'
import { useFindingsFacets, type Facets, type FacetsQuery } from '@/composables/useFindingsFacets'
import { panelFindingsQuery, panelQuery } from '@/dashboards/panelFilters'
import { countOf, fmt, type ScannerLens } from '@/lib/scannerLens'

const props = withDefaults(
  defineProps<{
    scanner: ScannerLens
    /** the screen's facets read; without it the card reads its own for `query` */
    facets?: Facets
    query?: FacetsQuery | null
    /** how many namespaces it lists; a dashboard panel sets it from its height */
    limit?: number
    /** a dashboard panel's own filters (issue 999) */
    filters?: ViewPreset | null
  }>(),
  { facets: undefined, query: undefined, limit: 10, filters: null },
)

const router = useRouter()
const { facets, settled, failed } = useFindingsFacets(
  () => props.facets,
  () => props.query && panelQuery(props.query, props.filters),
)

const namespaces = computed(() =>
  (facets.value.namespaces ?? [])
    .map((b) => ({ key: b.key, count: countOf(b, props.scanner) }))
    .filter((b) => b.count > 0)
    .slice(0, props.limit),
)

const findingsRoute = (query: Record<string, string>) => ({
  path: '/findings',
  query: panelFindingsQuery(props.filters, query),
})
function goFindings(query: Record<string, string>) {
  void router.push(findingsRoute(query))
}
</script>

<template>
  <section class="tbl-card">
    <div class="card-head">
      <div>
        <h2>Per namespace</h2>
        <p class="card-sub">top {{ limit }} by findings</p>
      </div>
      <UiButton variant="mini" @click="router.push('/images')">View inventory</UiButton>
    </div>
    <UiSkeleton
      v-if="!settled"
      class="skel-pad"
      :height="220"
      radius="sm"
      label="Loading namespaces"
    />
    <p v-else-if="failed" class="empty-row" role="alert">Namespace counts unavailable.</p>
    <p v-else-if="namespaces.length === 0" class="empty-row">No namespace data in range.</p>
    <div v-else class="tbl-wrap">
      <table class="tbl tbl-dense tbl-hover">
        <thead>
          <tr>
            <th>Namespace</th>
            <th class="r fit">Findings</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="n in namespaces"
            :key="n.key"
            :title="`Open findings in ${n.key}`"
            @click="goFindings({ namespace: n.key })"
          >
            <td class="mono-cell ns-link">
              <RowLink :to="findingsRoute({ namespace: n.key })" @open="goFindings({ namespace: n.key })">
                {{ n.key }}<AppIcon class="cell-go" name="chevron" :size="11" />
              </RowLink>
            </td>
            <td class="r fit mono-cell sm strong">{{ fmt(n.count) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 10px;
}
.card-head h2 {
  margin: 0;
  font-size: var(--text-card-title);
  font-weight: 600;
}
.card-sub {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.strong {
  font-weight: 700;
  color: var(--ink);
}
.skel-pad {
  margin: 0 16px 14px;
}
/* the affordance carrier — same convention as the grid's cve-link */
.ns-link {
  transition: color var(--dur-quick);
}
.tbl-hover tbody tr:hover .ns-link {
  color: var(--coral-text);
  text-decoration: underline;
  text-underline-offset: 3px;
}
@media (prefers-reduced-motion: reduce) {
  .ns-link {
    transition: none;
  }
}
</style>

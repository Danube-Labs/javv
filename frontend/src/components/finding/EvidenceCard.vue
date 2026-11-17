<script setup lang="ts">
/**
 * Per-scanner evidence, transposed (issue 434 ruling: specimen B): with exactly two scanners
 * the classic 8-column × 2-row table wasted the shape — scanners are COLUMNS and attributes
 * are rows, so a disagreement reads side-by-side per attribute. Still A-3: verbatim per
 * scanner, never reconciled; an absent scanner keeps its column with an explicit note.
 * Skin = the shared kit (`.tbl` family), chrome = DetailCard — nothing bespoke.
 */
import { computed } from 'vue'

import EpssBar from '@/components/chips/EpssBar.vue'
import ScannerTag from '@/components/chips/ScannerTag.vue'
import SevChip from '@/components/chips/SevChip.vue'
import StateTag from '@/components/chips/StateTag.vue'
import DetailCard from '@/components/finding/DetailCard.vue'
import AppIcon from '@/components/ui/AppIcon.vue'
import { SCANNER_ORDER } from '@/findings/detailViewModel'
import { fmtAt, num } from '@/findings/format'
import type { FindingRow } from '@/stores/findings'

const props = defineProps<{
  evidence: FindingRow[]
  missingScanners: string[]
  disagrees: boolean
}>()

const columns = computed(() =>
  SCANNER_ORDER.map((scanner) => ({
    scanner,
    row: props.evidence.find((r) => r.scanner === scanner) ?? null,
  })),
)

function verbatimDiffers(r: FindingRow): boolean {
  return r.severity.toLowerCase() !== r.severity_canonical
}
</script>

<template>
  <DetailCard title="Per-scanner evidence" sub="Each row shows the values that one scanner sent." flush>
    <div class="tbl-wrap">
      <table class="tbl tbl-dense compare">
        <thead>
          <tr>
            <th class="attr-col"></th>
            <th v-for="c in columns" :key="c.scanner"><ScannerTag :name="c.scanner" /></th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="attr">Severity</td>
            <td v-for="c in columns" :key="c.scanner">
              <template v-if="c.row">
                <SevChip :level="c.row.severity_canonical" />
                <span v-if="verbatimDiffers(c.row)" class="mono-cell sm verbatim" :title="'verbatim from ' + c.scanner">“{{ c.row.severity }}”</span>
              </template>
              <span v-else class="absent-note">no current finding</span>
            </td>
          </tr>
          <tr>
            <td class="attr">CVSS</td>
            <td v-for="c in columns" :key="c.scanner" class="mono-cell sm"><template v-if="c.row">{{ num(c.row.cvss) }}</template><span v-else class="muted-dash">-</span></td>
          </tr>
          <tr>
            <td class="attr">Package</td>
            <td v-for="c in columns" :key="c.scanner" class="mono-cell sm cell-cut" :title="c.row?.package_name || undefined"><template v-if="c.row?.package_name">{{ c.row.package_name }}</template><span v-else class="muted-dash">-</span></td>
          </tr>
          <tr>
            <td class="attr">Fixed in</td>
            <td v-for="c in columns" :key="c.scanner">
              <span v-if="c.row?.fixed_version" class="mono-cell sm ver-fix">{{ c.row.fixed_version }}</span>
              <span v-else-if="c.row" class="ver-none">no fix</span>
              <span v-else class="muted-dash">-</span>
            </td>
          </tr>
          <tr>
            <td class="attr">EPSS</td>
            <td v-for="c in columns" :key="c.scanner">
              <EpssBar v-if="c.row" :v="c.row.epss" />
              <span v-else class="muted-dash">-</span>
            </td>
          </tr>
          <tr>
            <td class="attr">State</td>
            <td v-for="c in columns" :key="c.scanner">
              <StateTag v-if="c.row" :state="c.row.state" />
              <span v-else class="muted-dash">-</span>
            </td>
          </tr>
          <tr>
            <td class="attr">Last seen</td>
            <td v-for="c in columns" :key="c.scanner" class="mono-cell sm"><template v-if="c.row">{{ fmtAt(c.row.last_seen_at) }}</template><span v-else class="muted-dash">-</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="disagrees" class="card-notes">
      <p class="evidence-note evidence-warn">
        <AppIcon name="alert" :size="12" /> The scanners give different severities. Each row shows the
        severity that its scanner sent.
      </p>
    </div>
  </DetailCard>
</template>

<style scoped>
/* a value with no space (a Go module path, a pseudo-version) would set the width of its column and
   push the other scanner out of the card: both scanner columns share the width, a package name
   keeps one line with its full name as the hover text, and the other values wrap (issue 1231, E1) */
.compare {
  table-layout: fixed;
}
.compare tbody td {
  overflow-wrap: anywhere;
}
.compare .cell-cut {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* three panels share the row from 1280px, where a scanner column has about 100px: the label
   column and the side padding give the room that a state tag or a severity chip needs (issue
   1231, operator ruling N of 2026-11-17 on built pictures) */
.compare .attr-col {
  width: 92px;
}
.compare.compare thead th,
.compare.compare tbody td {
  padding-left: 8px;
  padding-right: 8px;
}
.compare .attr {
  font-family: var(--font-mono);
  font-size: var(--text-table-header);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--soft);
}
.evidence-note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: var(--text-sm);
  color: var(--soft);
  line-height: 1.5;
}
.verbatim {
  margin-left: 8px;
  color: var(--soft);
}
.ver-fix {
  color: var(--teal-text);
}
.ver-none {
  color: var(--ver-none-fg);
  font-style: italic;
  font-size: var(--text-sm);
}
.absent-note {
  color: var(--soft);
  font-size: var(--text-sm);
  font-style: italic;
}
.evidence-warn {
  color: var(--ink);
}
.evidence-warn svg {
  color: var(--sev-high-fg);
  flex: none;
}
</style>

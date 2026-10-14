<script setup lang="ts">
/**
 * Guide (issue 341): how to read JAVV, in plain words. "On this page" is the shared section
 * menu, sticky on the left and following the scroll; each section is a card. Reachable from
 * the Help nav group by every signed-in user, and live before any cluster enrolls
 * (`isColdStart` exempts the `help` section). Static content: no reads, so nothing to log.
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { GUIDE_SECTIONS } from '@/about/guide'
import { useActiveSection } from '@/about/useActiveSection'
import { SECTION_BODY } from '@/components/about/guide/sections'
import SettingsCard from '@/components/settings/SettingsCard.vue'
import SectionNav from '@/components/ui/SectionNav.vue'

const route = useRoute()
const active = useActiveSection()

// the current query rides along, so jumping to a section keeps the range and the cluster
const navItems = computed(() =>
  GUIDE_SECTIONS.map((s) => ({
    key: s.id,
    label: s.title,
    icon: s.icon,
    to: { query: route.query, hash: `#${s.id}` },
  })),
)
</script>

<template>
  <div class="screen">
    <div class="screen-head">
      <div class="head-card head-card-fluid">
        <h1>How to read JAVV</h1>
        <p class="head-note">what the screens and the short labels mean, in plain words</p>
      </div>
    </div>
    <div class="guide-layout">
      <SectionNav :items="navItems" :active="active" label="On this page" current="location" />
      <div class="guide-cards">
        <div v-for="s in GUIDE_SECTIONS" :id="s.id" :key="s.id" class="guide-anchor">
          <SettingsCard :title="s.title" :subtitle="s.summary">
            <div class="guide-body"><component :is="SECTION_BODY[s.id]" /></div>
          </SettingsCard>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.guide-layout {
  display: grid;
  grid-template-columns: var(--section-nav-w) minmax(0, 1fr);
  gap: var(--grid-gap);
  align-items: start;
}
.guide-cards {
  display: flex;
  flex-direction: column;
  gap: var(--grid-gap);
}
.guide-anchor {
  scroll-margin-top: var(--space-4);
}
.guide-body {
  padding-top: 10px;
}
/* The guide's cards hold only prose, so each head is a band in the table-head colors to mark
   where a section starts (operator ruling on A/B specimens, 2026-10-14). Settings shares the
   card and keeps its plain head: there the band would stack on the tables inside the cards. */
.guide-anchor :deep(.card-head) {
  background: var(--table-head-bg);
  border-bottom-color: var(--table-head-line);
}
.guide-anchor :deep(.card-head h2) {
  color: var(--table-head-fg);
}
.guide-anchor :deep(.card-sub) {
  color: var(--side-fg);
}
@media (width <= 1100px) {
  .guide-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

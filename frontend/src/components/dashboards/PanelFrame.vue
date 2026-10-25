<script setup lang="ts">
/**
 * The card for a catalog panel that has none of its own (Triage progress lives inside a
 * Contributors section card): the Overview card skin, the panel's name and one line, then the
 * panel. It never clips: the card draws its own --shadow outside its box, and a panel taller
 * than its slot scrolls in the slot the dashboard gives it, not here.
 */
defineProps<{ title: string; line: string }>()
</script>

<template>
  <section class="panel-frame">
    <div class="pf-head">
      <h2>{{ title }}</h2>
      <p class="pf-line">{{ line }}</p>
    </div>
    <div class="pf-body"><slot /></div>
  </section>
</template>

<style scoped>
.panel-frame {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--r);
  box-shadow: var(--shadow);
}
.pf-head {
  padding: 14px 16px 0;
}
.pf-head h2 {
  margin: 0;
  font-size: var(--text-card-title);
  font-weight: 600;
}
.pf-line {
  margin: 2px 0 0;
  font-size: var(--text-sm);
  color: var(--soft);
}
.pf-body {
  padding: 10px 16px 14px;
}
</style>

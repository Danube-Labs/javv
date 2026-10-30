<script setup lang="ts">
/**
 * THE search box: a magnifier and a bare input in the bordered row of base.css (`.search-box`,
 * issue 1053), so the hover wash and line and the coral line on focus are owned once, in the skin.
 * `card` is the same box as the search card over a filter list (`.facet-search`). The class and the
 * style of a screen place the row; every other attribute (`placeholder`, `aria-*`, a key handler)
 * lands on the input. A screen that applies its search on Enter can give the value without taking
 * the changes back: the box then keeps what the user types until the screen gives a new value.
 */
import { computed, useAttrs } from 'vue'

import AppIcon from './AppIcon.vue'

defineOptions({ inheritAttrs: false })
withDefaults(defineProps<{ card?: boolean }>(), { card: false })
const model = defineModel<string>({ default: '' })

const attrs = useAttrs()
const ROW = ['class', 'style']
const rowAttrs = computed(() => Object.fromEntries(Object.entries(attrs).filter(([k]) => ROW.includes(k))))
const inputAttrs = computed(() => Object.fromEntries(Object.entries(attrs).filter(([k]) => !ROW.includes(k))))
</script>

<template>
  <div :class="card ? 'facet-search' : 'search-box'" v-bind="rowAttrs">
    <AppIcon name="search" :size="card ? 14 : 13" />
    <input v-model="model" v-bind="inputAttrs" />
  </div>
</template>

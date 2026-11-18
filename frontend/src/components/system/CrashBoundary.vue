<script setup lang="ts">
/**
 * Wraps the routed page inside the shell (SCREENS §18): when the page fails while it is drawn,
 * the error page takes its place and the sidebar and top bar stay usable. Every caught error is
 * logged; `replacesPage` decides which ones replace the page.
 */
import { onErrorCaptured, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ErrorPage from '@/components/system/ErrorPage.vue'
import UiButton from '@/components/ui/UiButton.vue'
import { logger } from '@/lib/logger'
import { errorMessage, errorStack, pageCrashed, replacesPage } from '@/system/crash'

const route = useRoute()
const router = useRouter()

onErrorCaptured((err, _instance, info) => {
  // message before info: a console preview shows only the first five fields, and the message is
  // the one that says what went wrong
  const fields = { route: route.path, message: errorMessage(err), info, stack: errorStack(err) }
  if (replacesPage(info)) {
    logger.error('page crashed', fields)
    pageCrashed.value = true
  } else {
    logger.error('page error', fields)
  }
  return false
})

watch(
  () => route.fullPath,
  () => {
    pageCrashed.value = false
  },
)

function toOverview() {
  pageCrashed.value = false
  void router.push({ name: 'overview' })
}
</script>

<template>
  <ErrorPage
    v-if="pageCrashed"
    code="Error"
    title="JAVV cannot show this page"
    hint="An error occurred when JAVV showed this page. Your data did not change. Try again, or go back to Overview."
  >
    <UiButton variant="primary" @click="pageCrashed = false">Try again</UiButton>
    <UiButton variant="control" @click="toOverview">Back to Overview</UiButton>
  </ErrorPage>
  <slot v-else />
</template>

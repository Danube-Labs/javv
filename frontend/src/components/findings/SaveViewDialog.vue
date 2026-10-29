<script setup lang="ts">
/**
 * "Save view" (M9f slice 4): names the CURRENT workbench — lens (negation included) + columns/
 * density/sort/window — and stores it server-side (C-6: durable, visible to every user). The
 * capture itself is computed by the owning screen; this dialog only names and posts it.
 */
import { computed, ref } from 'vue'

import { createViewApiV1ViewsPost, type ViewPreset, type ViewWorkbench } from '@/api/generated'
import SettingsInput from '@/components/settings/SettingsInput.vue'
import ModalShell from '@/components/ui/ModalShell.vue'
import UiButton from '@/components/ui/UiButton.vue'
import UiField from '@/components/ui/UiField.vue'
import { FINDINGS_FIELDS } from '@/filters/fields.config'
import { presetSummary } from '@/findings/savedViews'
import { logger } from '@/lib/logger'
import { useToastStore } from '@/stores/toast'

const props = defineProps<{ preset: ViewPreset; workbench: ViewWorkbench }>()
const toast = useToastStore()

const open = ref(false)
const name = ref('')
const description = ref('')
const saving = ref(false)

const summary = computed(() => presetSummary(FINDINGS_FIELDS, props.preset))

function show() {
  name.value = ''
  description.value = ''
  open.value = true
}

async function save() {
  const trimmed = name.value.trim()
  if (!trimmed) {
    toast.info('A view needs a name.')
    return
  }
  saving.value = true
  try {
    const { response } = await createViewApiV1ViewsPost({
      body: { name: trimmed, description: description.value.trim(), preset: props.preset, workbench: props.workbench },
    })
    if (response?.ok) {
      toast.success(`View “${trimmed}” saved`)
      open.value = false
    } else {
      logger.warn('view_save_failed', { status: response?.status })
      toast.error(response?.status === 422 ? 'These filters can\'t be saved as a view.' : 'Saving the view failed. Try again.')
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <UiButton variant="control" @click="show">Save view</UiButton>
  <ModalShell v-if="open" title="Save this view" subtitle="Filters, columns and time window, reusable by everyone" :width="440" @close="open = false">
    <p class="svd-summary">{{ summary }}</p>
    <UiField label="Name" for="svd-name">
      <SettingsInput id="svd-name" v-model="name" prose :maxlength="128" placeholder="e.g. Critical KEV backlog" @keydown.enter="save" />
    </UiField>
    <UiField label="Description" hint="optional" for="svd-description">
      <SettingsInput
        id="svd-description"
        v-model="description"
        prose
        :maxlength="1024"
        placeholder="What this view is for"
        @keydown.enter="save"
      />
    </UiField>
    <template #actions>
      <UiButton variant="control" @click="open = false">Cancel</UiButton>
      <UiButton variant="primary" :disabled="saving" @click="save">Save view</UiButton>
    </template>
  </ModalShell>
</template>

<style scoped>
.svd-summary {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--soft);
  font-style: italic;
}
</style>

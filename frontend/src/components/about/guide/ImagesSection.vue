<script setup lang="ts">
import { filterLabel } from '@/about/glossary'
import { FINDINGS_FIELDS } from '@/filters/fields.config'

import GuideProse from './GuideProse.vue'

const image = filterLabel(FINDINGS_FIELDS, 'image')
const tag = filterLabel(FINDINGS_FIELDS, 'tag')
const attribute = filterLabel(FINDINGS_FIELDS, 'attr')
const noTag = filterLabel(FINDINGS_FIELDS, 'untagged')
</script>

<template>
  <GuideProse>
    <p>
      A tag like <code class="mono">nginx:1.27</code> is a name that can point at different contents over
      time. JAVV tracks the <strong>digest</strong>, the fingerprint of the exact contents. If you
      rebuild and push the same tag, it is a new image with its own findings.
    </p>
    <p>
      An image's page lists its build history: every time the digest behind its tag changed, as scanned.
    </p>
    <p>
      On Findings, the <span class="ui-name">{{ image }}</span> filter finds all the tags of an image. To
      see one tag, add the <span class="ui-name">{{ tag }}</span> filter. To see the findings of images that
      have no tag, use <span class="ui-name">{{ noTag }}</span> in <span class="ui-name">{{ attribute }}</span>.
      For example, a pod can run an image by its digest only.
    </p>
  </GuideProse>
</template>

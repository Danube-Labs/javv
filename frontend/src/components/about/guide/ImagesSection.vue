<script setup lang="ts">
import GuideProse from './GuideProse.vue'
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
      On Findings, the <strong>Image</strong> filter finds all the tags of an image. To see one tag, add
      the <strong>Tag</strong> filter. To see the images that have no tag, use <strong>No tag</strong> in
      Attribute. For example, a pod can run an image by its digest only.
    </p>
  </GuideProse>
</template>

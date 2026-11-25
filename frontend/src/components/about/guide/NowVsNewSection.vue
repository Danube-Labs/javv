<script setup lang="ts">
import { filterLabel } from '@/about/glossary'
import { FINDINGS_FIELDS } from '@/filters/fields.config'

import GuideProse from './GuideProse.vue'

const newInRange = filterLabel(FINDINGS_FIELDS, 'new')
</script>

<template>
  <GuideProse>
    <p>Two questions look alike, and JAVV answers them in different places.</p>
    <ul>
      <li>
        <strong>What is vulnerable now?</strong> The findings and images tables. They list everything
        the latest scans still report.
      </li>
      <li>
        <strong>What arrived in this range?</strong> The Scan ingest and New findings strips, and the
        <span class="ui-name">{{ newInRange }}</span> filter. The New findings strip shows the findings
        that JAVV first saw in each day or hour, by severity. The filter keeps only the findings that
        JAVV first saw in the range. It uses the range of the strips, so the two count the same findings.
        A quiet range shows 0.
      </li>
    </ul>
  </GuideProse>
</template>

// @vitest-environment node
/**
 * Raw form fields outside the kit (issue 1055, G1 option B). ESLint refuses an `input`, `select` or
 * `textarea` in a `.vue` file outside `components/ui/`, with the project's own config, so this spec
 * fails if the rule is switched off or narrowed. A place that keeps a raw field says why, and the
 * list of those places is fixed here: a new one is a decision for review, not a silent comment.
 */
import { ESLint } from 'eslint'
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = join(__dirname, '..', '..')
const SRC = join(ROOT, 'src')
const RULE = 'vue/no-restricted-html-elements'
const RAW = `<template>
  <div>
    <input v-model="a" />
    <select v-model="a"><option>x</option></select>
    <textarea v-model="a" />
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
const a = ref('')
</script>
`

const eslint = new ESLint({ cwd: ROOT })
const ruleHits = async (code: string, filePath: string) =>
  (await eslint.lintText(code, { filePath }))[0]!.messages.filter((m) => m.ruleId === RULE)

function vueFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
    e.isDirectory() ? vueFiles(join(dir, e.name)) : e.name.endsWith('.vue') ? [join(dir, e.name)] : [],
  )
}

describe('raw form fields outside the kit', () => {
  it('ESLint refuses a raw text box, dropdown and text area in a view, and names the kit pieces', async () => {
    const hits = await ruleHits(RAW, 'src/views/ProbeView.vue')
    expect(hits.map((m) => m.line)).toEqual([3, 4, 5])
    expect(hits[0]!.message).toContain('UiTextBox')
  }, 30_000)

  it('ESLint refuses them in any component folder too', async () => {
    expect(await ruleHits(RAW, 'src/components/findings/Probe.vue')).toHaveLength(3)
  }, 30_000)

  it('the kit itself may draw the raw fields', async () => {
    expect(await ruleHits(RAW, 'src/components/ui/UiProbe.vue')).toEqual([])
  }, 30_000)

  it('each place that keeps a raw field gives its reason, and the list of places is fixed', () => {
    const disables = vueFiles(SRC).flatMap((f) =>
      readFileSync(f, 'utf8')
        .split('\n')
        .filter((line) => line.includes(`eslint-disable-next-line ${RULE}`))
        .map((line) => ({ file: relative(SRC, f), reason: line.split(' -- ')[1]?.replace('-->', '').trim() ?? '' })),
    )
    expect(disables.map((d) => d.file).sort()).toEqual([
      'components/chrome/CommandPalette.vue',
      'components/dashboards/ImportDashboardsDialog.vue',
      'components/settings/ChipsInput.vue',
      'views/InspectView.vue',
    ])
    for (const d of disables) expect(d.reason.length, `${d.file} gives a reason`).toBeGreaterThan(15)
  })
})

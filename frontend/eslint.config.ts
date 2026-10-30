import { globalIgnores } from 'eslint/config'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import pluginVue from 'eslint-plugin-vue'
import pluginVitest from '@vitest/eslint-plugin'
import pluginOxlint from 'eslint-plugin-oxlint'

// To allow more languages other than `ts` in `.vue` files, uncomment the following lines:
// import { configureVueProject } from '@vue/eslint-config-typescript'
// configureVueProject({ scriptLangs: ['ts', 'tsx'] })
// More info at https://github.com/vuejs/eslint-config-typescript/#advanced-setup

export default defineConfigWithVueTs(
  {
    name: 'app/files-to-lint',
    files: ['**/*.{vue,ts,mts,tsx}', 'server/**/*.mjs'],
  },

  globalIgnores(['**/dist/**', '**/dist-ssr/**', '**/coverage/**', 'src/api/generated/**']),

  ...pluginVue.configs['flat/essential'],
  vueTsConfigs.recommended,

  {
    ...pluginVitest.configs.recommended,
    files: ['src/**/__tests__/*'],
  },

  {
    name: 'app/no-raw-console',
    files: ['src/**/*.{ts,mts,tsx,vue}', 'server/**/*.mjs'],
    // FE analog of "never print()": src/lib/logger.ts in the browser, server/log.mjs in the server
    rules: { 'no-console': 'error' },
  },

  {
    name: 'app/kit-form-fields',
    files: ['src/**/*.vue'],
    ignores: ['src/components/ui/**'],
    // a form field is a kit piece, so the look of a box lives once, in the kit (issue 1055, G1 option B)
    rules: {
      'vue/no-restricted-html-elements': [
        'error',
        {
          element: ['input', 'select', 'textarea'],
          message:
            'Use a kit piece from components/ui/ (UiTextBox, UiTextArea, UiSelect, UiSearchBox), or give the reason in an eslint-disable comment.',
        },
      ],
    },
  },

  ...pluginOxlint.buildFromOxlintConfigFile('.oxlintrc.json'),
)

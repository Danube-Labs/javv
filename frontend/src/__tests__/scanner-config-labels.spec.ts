/**
 * The scanner cards of Settings › Scanning show each scanner setting by a label, with the key of
 * the scanner in the hover text (issue 1140, step 2.4). The keys are the fields of TrivyConfig and
 * GrypeConfig in scanner/src/scanner/config.py.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ScannerConfigCard from '@/components/settings/ScannerConfigCard.vue'
import { scannerSettingLabel } from '@/lib/scannerSettingLabel'

describe('scannerSettingLabel', () => {
  it('gives a label for each setting of both scanners', () => {
    const trivy = ['scanners', 'ignore_unfixed', 'severities', 'pkg_types', 'timeout']
    const grype = ['only_fixed', 'scope', 'scan_timeout']
    for (const key of [...trivy, ...grype]) expect(scannerSettingLabel(key)).not.toBe(key)
    expect(scannerSettingLabel('scan_timeout')).toBe('Scan time limit (seconds)')
    expect(scannerSettingLabel('ignore_unfixed')).toBe('Skip CVEs with no fix')
  })

  it('shows a key it does not know as it is', () => {
    expect(scannerSettingLabel('new_flag')).toBe('new_flag')
  })
})

describe('ScannerConfigCard', () => {
  it('shows the labels, with the key in the hover text, and names the database schema', () => {
    const w = mount(ScannerConfigCard, {
      props: {
        scanner: 'grype',
        version: '0.120.1',
        dbVersion: 'v6.1.10',
        dbBuilt: null,
        config: { tuning: { scan_timeout: 600, only_fixed: false, new_flag: 'x' }, scope: {} },
      },
    })
    const keys = w.findAll('.cfg-key').map((k) => [k.text(), k.attributes('title')])
    expect(keys).toContainEqual(['Scan time limit (seconds)', 'scan_timeout'])
    expect(keys).toContainEqual(['Only CVEs with a fix', 'only_fixed'])
    expect(keys).toContainEqual(['new_flag', 'new_flag'])
    expect(w.text()).toContain('Vulnerability database schema')
    expect(w.text()).not.toContain('vuln DB')
  })

  it('says where the version and the settings are set, with no words of one deploy tool', () => {
    const w = mount(ScannerConfigCard, {
      props: { scanner: 'trivy', version: '0.76.2', dbVersion: '2', dbBuilt: null, config: null },
    })
    const tag = w.find('.gitops-tag')
    expect(tag.text()).toBe('set where it runs')
    expect(tag.attributes('title')).toBe(
      'The version and the settings of the scanner are set where it runs: its image tag and its ' +
        'environment variables. JAVV does not change them, and each scan records the scanner version.',
    )
    expect(w.html()).not.toMatch(/GitOps|operator-managed/)
  })
})

/**
 * The evidence card in the head row (issue 1205): the ruled text of the text round, group 1
 * (comments 6880398386 and 6881237662). The package menu of the head band lists the other
 * packages, so the card has no line for them.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EvidenceCard from '@/components/finding/EvidenceCard.vue'

const row = (scanner: string, severity: string) =>
  ({
    finding_key: `fk-${scanner}`,
    cve_id: 'CVE-2026-0001',
    scanner,
    severity,
    severity_canonical: severity.toLowerCase(),
    state: 'open',
    package_name: 'openssl',
    installed_version: '3.0.1',
    fixed_version: null,
  }) as never

const card = (disagrees: boolean) =>
  mount(EvidenceCard, {
    props: {
      evidence: [row('trivy', 'HIGH'), row('grype', disagrees ? 'Medium' : 'High')],
      missingScanners: [],
      disagrees,
    },
  })

describe('the evidence card (issue 1205, text round group 1)', () => {
  it('says under its title what a row shows', () => {
    expect(card(false).text()).toContain('Each row shows the values that one scanner sent.')
    expect(card(false).text()).not.toContain('no black box')
  })

  it('has no note when the scanners agree', () => {
    expect(card(false).text()).not.toContain('Scanners agree')
    expect(card(false).find('.evidence-note').exists()).toBe(false)
  })

  it('says it when the scanners give different severities', () => {
    expect(card(true).find('.evidence-note').text()).toBe(
      'The scanners give different severities. Each row shows the severity that its scanner sent.',
    )
  })

  it('has no line for the other packages: the package menu of the head band lists them', () => {
    expect(card(false).text()).not.toContain('also affects')
  })
})

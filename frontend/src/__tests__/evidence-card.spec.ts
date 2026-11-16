/**
 * The evidence card in the head row (issue 1205): the ruled text of the text round, group 1
 * (comments 6880398386 and 6881237662). The package menu of the head band lists the other
 * packages, so the card has no line for them.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import EvidenceCard from '@/components/finding/EvidenceCard.vue'

import { declarations } from './helpers/componentStyle'

const row = (scanner: string, severity: string, packageName = 'openssl') =>
  ({
    finding_key: `fk-${scanner}`,
    cve_id: 'CVE-2026-0001',
    scanner,
    severity,
    severity_canonical: severity.toLowerCase(),
    state: 'open',
    package_name: packageName,
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

const LONG = 'go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc'

const packageCells = (w: ReturnType<typeof mount>) => {
  const tr = w.findAll('tbody tr').find((t) => t.find('td.attr').text() === 'Package')!
  return tr.findAll('td').slice(1)
}

describe('a long value stays in the evidence card (issue 1231, E1 on built pictures)', () => {
  it('cuts the package name on one line and gives its full name as the hover text', () => {
    const w = mount(EvidenceCard, {
      props: { evidence: [row('trivy', 'HIGH', LONG), row('grype', 'High', LONG)], missingScanners: [], disagrees: false },
    })
    for (const td of packageCells(w)) {
      expect(td.classes()).toContain('cell-cut')
      expect(td.attributes('title')).toBe(LONG)
      expect(td.text()).toBe(LONG)
    }
  })

  it('gives a name with < and & as text, in the cell and in the hover text', () => {
    const name = 'a<b>&c'
    const w = mount(EvidenceCard, { props: { evidence: [row('trivy', 'HIGH', name)], missingScanners: [], disagrees: false } })
    const [trivy] = packageCells(w)
    expect(trivy!.text()).toBe(name)
    expect(trivy!.attributes('title')).toBe(name)
    expect(trivy!.find('b').exists()).toBe(false)
  })

  it('has no hover text in the cell of a scanner with no finding', () => {
    const w = mount(EvidenceCard, { props: { evidence: [row('trivy', 'HIGH', LONG)], missingScanners: ['grype'], disagrees: false } })
    const [, grype] = packageCells(w)
    expect(grype!.attributes('title')).toBeUndefined()
    expect(grype!.find('.muted-dash').exists()).toBe(true)
  })

  it('gives both scanner columns the same width and wraps the other values where they must', () => {
    const file = 'components/finding/EvidenceCard.vue'
    expect(declarations(file, '.compare')).toMatchObject({ 'table-layout': 'fixed' })
    expect(declarations(file, '.compare tbody td')).toMatchObject({ 'overflow-wrap': 'anywhere' })
    expect(declarations(file, '.compare .cell-cut')).toMatchObject({
      overflow: 'hidden',
      'text-overflow': 'ellipsis',
      'white-space': 'nowrap',
    })
  })
})

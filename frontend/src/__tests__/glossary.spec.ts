/**
 * The Guide's glossary (issue 341): a term that is also a findings filter must show that
 * filter's live label, so renaming the filter can't leave the glossary describing a label
 * nobody sees. And the copy stays plain: no em dashes (operator ruling 2026-10-01).
 */
import { describe, expect, it } from 'vitest'

import { GLOSSARY, filterLabel, glossaryTerm } from '@/about/glossary'
import { FINDINGS_FIELDS, type FilterField } from '@/filters/fields.config'

describe('filterLabel', () => {
  const fields: FilterField[] = [
    { key: 'severity', label: 'Severity', type: 'terms', param: 'severity' },
    {
      key: 'attr',
      label: 'Attribute',
      type: 'flags',
      values: [{ key: 'kev', param: 'kev', label: 'KEV' }],
    },
  ] as FilterField[]

  it("returns a field's own label", () => {
    expect(filterLabel(fields, 'severity')).toBe('Severity')
  })
  it("returns a flags field's value label", () => {
    expect(filterLabel(fields, 'kev')).toBe('KEV')
  })
  it('returns null for a key no field knows', () => {
    expect(filterLabel(fields, 'nope')).toBeNull()
  })
})

describe('GLOSSARY', () => {
  it('every filter term resolves to a live findings filter label', () => {
    const keys = GLOSSARY.flatMap((e) => ('filter' in e.term ? [e.term.filter] : []))
    expect(keys.length).toBeGreaterThan(0)
    expect(keys.filter((k) => filterLabel(FINDINGS_FIELDS, k) === null)).toEqual([])
  })

  it('shows the filter labels the findings screen shows', () => {
    const terms = GLOSSARY.map(glossaryTerm)
    expect(terms).toContain('Fix available')
    expect(terms).toContain('Scanners disagree')
    expect(terms).toContain('SLA breached')
    expect(terms).toContain('New in range')
  })

  it('tells what Namespace is for each source of scans (issue 1152)', () => {
    const entry = GLOSSARY.find((e) => glossaryTerm(e) === 'Namespace')
    expect(entry?.body).toBe(
      'Where the image runs. For a Kubernetes cluster, the namespace. For a Nomad cluster, the ' +
        'Nomad job. For a Docker host, the Compose project, or the name of a container with no project.',
    )
  })

  it('has no duplicate terms', () => {
    const terms = GLOSSARY.map(glossaryTerm)
    expect(new Set(terms).size).toBe(terms.length)
  })

  it('has no em dashes in any term or definition', () => {
    for (const entry of GLOSSARY) {
      expect(`${glossaryTerm(entry)} ${entry.body}`).not.toContain('—')
    }
  })
})

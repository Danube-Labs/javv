/**
 * The Guide page's glossary (issue 341): the short labels people meet in tables and filters, in
 * plain words. A term that is also a findings filter takes its label from `FINDINGS_FIELDS` by
 * key, so renaming the filter renames the glossary entry instead of leaving it describing a
 * label nobody sees any more.
 */
import { FINDINGS_FIELDS, type FilterField } from '@/filters/fields.config'

/** What the entry shows beside its term: the same chip the app renders for it. */
export type GlossaryChip = 'kev' | 'epss' | 'disagree' | 'stale' | 'resolved'

export interface GlossaryEntry {
  /** A findings filter key, or a fixed term for labels that aren't filters. */
  term: { filter: string } | { text: string }
  chip?: GlossaryChip
  body: string
}

/** The label a findings filter shows: a field's own label, or one of a flags field's values. */
export function filterLabel(fields: readonly FilterField[], key: string): string | null {
  for (const field of fields) {
    if (field.key === key) return field.label
    if (field.type === 'flags') {
      const flag = field.values.find((v) => v.key === key)
      if (flag) return flag.label
    }
  }
  return null
}

export const GLOSSARY: readonly GlossaryEntry[] = [
  {
    term: { filter: 'kev' },
    chip: 'kev',
    body:
      'Listed in CISA’s Known Exploited Vulnerabilities catalog: attackers are known to use it. ' +
      'Only Grype reports it, so Trivy findings never carry it.',
  },
  {
    term: { text: 'EPSS' },
    chip: 'epss',
    body:
      'The Exploit Prediction Scoring System: the estimated chance that the CVE is exploited in ' +
      'the next 30 days. Only Grype reports it.',
  },
  {
    term: { filter: 'fixable' },
    body: 'The scanner names a version of the package that fixes this CVE.',
  },
  {
    term: { filter: 'disagree' },
    chip: 'disagree',
    body:
      'Trivy and Grype report the same CVE in the same package of this image, with different ' +
      'severities. Both findings stay as reported; JAVV doesn’t decide which one is right.',
  },
  {
    term: { filter: 'overdue' },
    body:
      'Past the deadline your SLA policy sets for its severity. The clock starts the first time ' +
      'either scanner reported the CVE on that image. Risk-accepted, not-affected and resolved ' +
      'findings never count.',
  },
  {
    term: { filter: 'new' },
    body: 'Keeps only findings first seen inside the selected range, so a quiet range shows 0.',
  },
  {
    term: { text: 'First seen' },
    body:
      'When this scanner first reported this finding on this image. Each scanner keeps its own, ' +
      'so the same CVE can show two different first-seen times.',
  },
  {
    term: { text: 'Last seen · Last scan' },
    body:
      'When the latest complete scan that reported this finding ran. Both labels show the same ' +
      'moment.',
  },
  {
    term: { text: 'Present' },
    body:
      'Reported by the latest complete scan of its image. The findings tables list present ' +
      'findings only; one the next scan no longer reports leaves them at once.',
  },
  {
    term: { text: 'Stale' },
    chip: 'stale',
    body:
      'JAVV can’t confirm the finding any more: its image hasn’t been scanned again for a while, ' +
      'or its scanner has gone silent. It isn’t a fix: once a scan reports the finding again, it ' +
      'goes back to its previous state.',
  },
  {
    term: { text: 'Resolved' },
    chip: 'resolved',
    body:
      'JAVV does not set it. A fix the scanner confirms shows as the finding leaving the tables, ' +
      'not as Resolved.',
  },
  {
    term: { filter: 'namespace' },
    body:
      'Where the image runs. For a Kubernetes cluster, the namespace. For a Nomad cluster, the ' +
      'Nomad job. For a Docker host, the Compose project, or the name of a container with no project.',
  },
  {
    term: { text: 'Digest' },
    body:
      'The fingerprint of an image’s exact contents (sha256:…). Two images with the same tag ' +
      'but different digests are different images.',
  },
]

export function glossaryTerm(entry: GlossaryEntry): string {
  return 'filter' in entry.term
    ? (filterLabel(FINDINGS_FIELDS, entry.term.filter) ?? entry.term.filter)
    : entry.term.text
}

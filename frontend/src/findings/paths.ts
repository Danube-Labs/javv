/**
 * The files where a scanner found the package of a finding (issue 1077). Each entry is ONE
 * finding of one scanner: the entries of a row are listed side by side, never added up or
 * joined, because the two scanners report different files for the same package.
 *
 * `total` is the stored `locations_total`. `null` means that the scan sent no paths (a scanner
 * before envelope schema 5, or a past row stored before them), which is not the same as `0`: a
 * scan that reported the package in no file.
 */
import type { FindingRow } from '@/stores/findings'

export interface FindingPaths {
  scanner: string
  digest: string | null
  total: number | null
  paths: string[]
}

const SCANNER_NAME: Record<string, string> = { trivy: 'Trivy', grype: 'Grype' }
export const scannerName = (s: string): string => SCANNER_NAME[s] ?? s

export function pathsOf(r: FindingRow): FindingPaths {
  return {
    scanner: r.scanner,
    digest: typeof r.image_digest === 'string' ? r.image_digest : null,
    total: r.locations_total ?? null,
    paths: r.locations ?? [],
  }
}

const plural = (n: number) => `${n} ${n === 1 ? 'path' : 'paths'}`

/** The cell text: "11 paths" for one finding; one number for each finding, "0 · 5", for more. */
export function countText(entries: readonly FindingPaths[]): string {
  if (entries.length === 1) {
    const t = entries[0]!.total
    return t === null ? '-' : plural(t)
  }
  return entries.map((e) => (e.total === null ? '-' : String(e.total))).join(' · ')
}

/* who an entry is for: the scanner, and the digest when the row holds more than one digest of
   its tag, else two numbers of one scanner cannot be told apart */
function whoOf(entries: readonly FindingPaths[]): (e: FindingPaths) => string {
  const many = new Set(entries.map((e) => e.digest)).size > 1
  return (e) => (many && e.digest ? `${scannerName(e.scanner)} on ${shortDigest(e.digest)}` : scannerName(e.scanner))
}

/** The hover text of a cell, so "-" and "0" are not read as the same thing. */
export function countTitle(entries: readonly FindingPaths[]): string {
  const name = whoOf(entries)
  return entries
    .map((e) => {
      const who = name(e)
      if (e.total === null) return `${who}: this scan did not report paths.`
      if (e.total === 0) return `${who}: the scanner gave no path.`
      return `${who}: ${plural(e.total)}.`
    })
    .join(' ')
}

/** The name a screen reader gives the button that opens the paths. */
export function openLabel(entries: readonly FindingPaths[]): string {
  const name = whoOf(entries)
  const counts = entries
    .map((e) => `${name(e)} ${e.total === null ? 'not reported' : e.total}`)
    .join(', ')
  return `Paths: ${counts}. Show the paths`
}

/** A row opens only when at least one of its findings has a path to show. */
export const hasPaths = (entries: readonly FindingPaths[]): boolean =>
  entries.some((e) => e.paths.length > 0)

/** The sentence over the list of one finding. */
export function foundText(e: FindingPaths, pkg: string, version: string | null): string {
  const who = scannerName(e.scanner)
  const what = version ? `${pkg} ${version}` : pkg
  if (e.total === null) return `This scan of ${who} did not report the paths of ${what}.`
  if (e.total === 0) return `${who} gave no path for ${what}.`
  return `${who} found ${what} at ${plural(e.total)} in this image. The finding counts one time.`
}

/** Said when JAVV keeps fewer paths than the scanner reported (the cap of 64, issue 1077 D2). */
export function keptText(e: FindingPaths): string | null {
  return e.total !== null && e.total > e.paths.length && e.paths.length > 0
    ? `JAVV keeps the first ${e.paths.length} of ${e.total} paths.`
    : null
}

/** The digest in a short form, for a row that holds findings of more than one digest. */
export const shortDigest = (d: string): string => {
  const [algo, hex] = d.includes(':') ? d.split(':', 2) : ['', d]
  return `${algo ? algo + ':' : ''}${(hex ?? '').slice(0, 12)}`
}

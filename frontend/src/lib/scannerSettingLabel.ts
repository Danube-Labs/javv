/** A scanner setting as people read it. The keys are the fields of `TrivyConfig` and `GrypeConfig`
 * in `scanner/src/scanner/config.py`, which every scan stamps in its `effective_config`. A key
 * that a newer scanner adds shows as it is until it gets a label here (issue 1140). */
const LABELS: Record<string, string> = {
  scanners: 'Checks',
  ignore_unfixed: 'Skip CVEs with no fix',
  severities: 'Severities',
  pkg_types: 'Package types',
  timeout: 'Time limit',
  only_fixed: 'Only CVEs with a fix',
  scope: 'Image layers',
  scan_timeout: 'Scan time limit (seconds)',
}

export function scannerSettingLabel(key: string): string {
  return LABELS[key] ?? key
}

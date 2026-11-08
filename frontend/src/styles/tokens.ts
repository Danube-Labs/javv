/**
 * Typed mirror of the severity/status token maps in tokens.css — the ONLY sanctioned way to
 * reference severity/status colors from script (chart option-builders, dynamic styles).
 * Severity is DATA ONLY (never brand); the six keys are the D46 canonical vocabulary.
 */
export const SEVERITIES = [
  'critical',
  'high',
  'medium',
  'low',
  'negligible',
  'unknown',
] as const
export type Severity = (typeof SEVERITIES)[number]

export interface SeverityTokens {
  fg: string
  bg: string
  line: string
  solid: string
}

const sevVar = (s: Severity, part: keyof SeverityTokens): string => `var(--sev-${s}-${part})`

export const SEV_COLOR: Record<Severity, SeverityTokens> = Object.fromEntries(
  SEVERITIES.map((s) => [
    s,
    { fg: sevVar(s, 'fg'), bg: sevVar(s, 'bg'), line: sevVar(s, 'line'), solid: sevVar(s, 'solid') },
  ]),
) as Record<Severity, SeverityTokens>

/**
 * Chart AREA colors (ECharts SVG can't resolve CSS vars in every context, so charts use
 * literals — same hexes as the `--sev-*-chart` tokens, pinned equal by the tokens unit test).
 * Language A (operator 2026-07-12): the ramp ESCALATES — critical/high keep the full
 * solids, the tail (low/negligible/unknown) recedes. Chips keep the `-solid` family.
 * Each level is a lightness step lighter than the last, so the bands separate in grayscale.
 */
export const CHART_SEV: Record<Severity, string> = {
  critical: '#c0271d',
  high: '#e2640f',
  medium: '#dba839',
  low: '#a5cae2',
  negligible: '#cbdad4',
  unknown: '#dfe7ee',
}

export const STATES = ['open', 'stale', 'ack', 'resolved'] as const
export type StateTone = (typeof STATES)[number]

export const STATE_COLOR: Record<StateTone, { fg: string; bg: string; line: string }> =
  Object.fromEntries(
    STATES.map((s) => [
      s,
      { fg: `var(--state-${s}-fg)`, bg: `var(--state-${s}-bg)`, line: `var(--state-${s}-line)` },
    ]),
  ) as Record<StateTone, { fg: string; bg: string; line: string }>

export const SCANNER_COLOR = {
  trivy: { fg: 'var(--scanner-trivy-fg)', bg: 'var(--scanner-trivy-bg)' },
  grype: { fg: 'var(--scanner-grype-fg)', bg: 'var(--scanner-grype-bg)' },
} as const

/** Chart-literal scanner series colors — same hexes as --scanner-*-fg (pinned by the tokens test). */
export const CHART_SCANNER: Record<'trivy' | 'grype', string> = {
  trivy: '#17685f',
  grype: '#5a4f9e',
}

/** The one-series accent for non-severity, non-scanner activity charts (the audit lens) —
 * same hex as --slate2 (pinned by the tokens test). Coral is in the red-orange of critical, so a
 * bar of triage activity read as a severity (issue 1140, R8). Severity charts stay on CHART_SEV. */
export const CHART_ACCENT = '#21384a'

/** Chart chrome literals — same hexes as the named tokens (pinned by the tokens test).
 * ECharts canvas can't resolve CSS vars, so charts read these instead of raw hexes. */
export const CHART_UI = {
  axisLine: '#e7e0d3', // --line
  splitLine: '#f0ebe0', // --line2
  label: '#5d6a74', // --soft
  tooltipBg: '#16232f', // --slate
  tooltipFg: '#f3eee6', // --side-brand-fg
  segBorder: '#ffffff', // --card — pie-segment separator on the card surface
} as const

/** Categorical palette for the package-type donut — hue-ALTERNATING so adjacent segments stay
 * distinct even when two buckets dominate (operator 2026-07-11: the teal ramp read all-green).
 * Decorative categorical coding, NOT severity; none of these equal a severity or scanner
 * series hex. First entry stays --teal (the brand-info anchor, pinned). */
export const CHART_PTYPE_RAMP = [
  '#1f8e84', // teal (--teal)
  '#5a7fb8', // slate blue
  '#c98d3f', // ochre
  '#a86f8e', // mauve
  '#6f9e5a', // olive
  '#4fb0a5', // aqua
  '#8c7f5a', // khaki
  '#b87f6f', // clay
  '#7c8a99', // grey-blue
] as const

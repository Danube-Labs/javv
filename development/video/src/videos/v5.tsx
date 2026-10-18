// Video 5: when a scanner stops sending results.
import { interpolate, spring } from 'remotion'
import shots from '../../public/v5/shots.json'
import { C, MONO, SANS, type Video } from '../engine'

const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const
const C1 = 140
const C2 = 160
const C3 = 170

const ACK = { label: 'Acknowledged', fg: '#1f5f8b', bg: '#e3eef7' }
const STALE = { label: 'Stale', fg: '#5f6368', bg: '#ececea' }

function StateBadge({ s, scale = 1 }: { s: { label: string; fg: string; bg: string }; scale?: number }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10, padding: '8px 18px', borderRadius: 999, background: s.bg, color: s.fg, fontSize: 26, fontWeight: 600, transform: `scale(${scale})` }}>
      <span style={{ width: 11, height: 11, borderRadius: '50%', background: s.fg }} />
      {s.label}
    </span>
  )
}

/** a finding over time: scans refresh it, the scanner goes silent, Stale, a scan returns, restored */
function Timeline({ frame: f }: { frame: number }) {
  const fps = 30
  const card = spring({ frame: f - 4, fps, config: { damping: 200 } })
  const X0 = 180
  const X1 = 1356
  const xAt = (t: number) => X0 + (X1 - X0) * t
  // the time cursor walks along the track over the three captions
  const cursor = interpolate(f, [10, C1, C1 + C2 - 30, C1 + C2 + 40, C1 + C2 + C3 - 30], [0.02, 0.32, 0.72, 0.82, 0.9], clamp)
  const scans = [0.06, 0.13, 0.2, 0.27, 0.86] // the last one is the scan that sees it again
  const silentFrom = 0.3
  const staleAt = 0.62
  const isStale = cursor >= staleAt && cursor < 0.86
  const restored = cursor >= 0.86
  // every change follows the time cursor, so nothing happens before "now" reaches it
  const flip = isStale ? interpolate(cursor, [staleAt, staleAt + 0.015], [0, 1], clamp) : restored ? interpolate(cursor, [0.86, 0.875], [0, 1], clamp) : 1
  const kept = interpolate(cursor, [staleAt, staleAt + 0.02], [0, 1], clamp) * (restored ? interpolate(cursor, [0.86, 0.88], [1, 0], clamp) : 1)

  return (
    <div style={{ position: 'absolute', inset: 0, background: C.bg, fontFamily: SANS }}>
      {/* the finding */}
      <div
        style={{
          position: 'absolute', left: 468, top: 120, width: 600, padding: '28px 34px', borderRadius: 20, background: C.card,
          boxShadow: '0 18px 50px rgb(22 35 47 / 12%)', border: `1px solid ${C.line}`, opacity: card, transform: `translateY(${(1 - card) * 24}px)`,
        }}
      >
        <div style={{ fontFamily: MONO, fontSize: 30, fontWeight: 700, color: C.ink }}>CVE-2026-73579</div>
        <div style={{ marginTop: 6, fontFamily: MONO, fontSize: 19, color: 'rgb(22 35 47 / 60%)' }}>libc6 · billing-3:2.1.0 · trivy</div>
        <div style={{ marginTop: 22, display: 'flex', alignItems: 'center', gap: 18, height: 52 }}>
          <StateBadge s={isStale ? STALE : ACK} scale={0.88 + 0.12 * flip} />
          <span style={{ fontFamily: MONO, fontSize: 17, color: C.coralText, opacity: kept, whiteSpace: 'nowrap' }}>
            kept: Acknowledged
          </span>
        </div>
      </div>

      {/* the time track */}
      <div style={{ position: 'absolute', left: X0, width: X1 - X0, top: 520, height: 4, borderRadius: 2, background: 'rgb(22 35 47 / 14%)' }} />
      <div
        style={{
          position: 'absolute', left: xAt(silentFrom), width: xAt(staleAt) - xAt(silentFrom), top: 500, height: 44, borderRadius: 10,
          background: 'rgb(236 126 84 / 14%)', border: `1px dashed ${C.coral}`, opacity: interpolate(f, [C1 + 10, C1 + 30], [0, 1], clamp),
        }}
      />
      <div style={{ position: 'absolute', left: xAt(silentFrom), width: xAt(staleAt) - xAt(silentFrom), top: 556, textAlign: 'center', fontFamily: MONO, fontSize: 17, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: C.coralText, opacity: interpolate(f, [C1 + 20, C1 + 40], [0, 1], clamp) }}>
        no results
      </div>
      {scans.map((t, i) => {
        const k = interpolate(cursor, [t, t + 0.012], [0, 1], clamp)
        const pop = 1 + 0.35 * Math.sin(Math.PI * k)
        return (
          <div key={i} style={{ position: 'absolute', left: xAt(t) - 14, top: 508, width: 28, height: 28, borderRadius: '50%', background: C.slate, transform: `scale(${k * pop})`, boxShadow: '0 0 0 5px rgb(22 35 47 / 10%)' }} />
        )
      })}
      <div style={{ position: 'absolute', left: X0, top: 470, fontFamily: MONO, fontSize: 16, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase', color: 'rgb(22 35 47 / 55%)' }}>
        scans
      </div>
      {/* the moment the sweep marks it Stale */}
      <div style={{ position: 'absolute', left: xAt(staleAt) - 1, top: 470, width: 2, height: 110, background: STALE.fg, opacity: interpolate(f, [C1 + 60, C1 + 75], [0, 1], clamp) }} />
      <div style={{ position: 'absolute', left: xAt(staleAt) + 10, top: 470, fontFamily: MONO, fontSize: 16, fontWeight: 700, color: STALE.fg, opacity: interpolate(f, [C1 + 60, C1 + 75], [0, 1], clamp), whiteSpace: 'nowrap' }}>
        STALE
      </div>
      {/* now */}
      <div style={{ position: 'absolute', left: xAt(cursor) - 2, top: 600, width: 4, height: 30, borderRadius: 2, background: C.coral }} />
      <div style={{ position: 'absolute', left: xAt(cursor) - 40, top: 640, width: 80, textAlign: 'center', fontFamily: MONO, fontSize: 16, fontWeight: 700, color: C.coralText }}>now</div>
    </div>
  )
}

export const v5: Video = {
  dir: 'v5',
  shots,
  title: 'When a scanner stops sending results',
  kicker: 'Triage · video 5 of 6',
  next: 'Next: see who changed what',
  steps: 3,
  intro: {
    component: Timeline,
    captions: [
      { step: 1, text: 'Each scan refreshes the findings that the scanner sees.', frames: C1 },
      { step: 1, text: 'If a scanner sends no results for too long, JAVV marks its findings Stale.', frames: C2 },
      { step: 1, text: 'JAVV keeps the old state. When a scan sees the finding again, JAVV restores it.', frames: C3 },
    ],
  },
  beats: [
    { shot: 'findings', step: 2, caption: 'This banner shows that a scanner is silent. The data of the cluster can be old.', spot: 'banner', wide: true },
    { shot: 'findings', step: 2, caption: 'The State filter counts the Stale findings.', spot: 'stateFacet' },
    { shot: 'findings', step: 2, caption: 'Open Scanner status from the side menu.', spot: 'statusLink', click: { box: 'statusLink', to: 'status', page: true } },
    { shot: 'status', step: 2, caption: 'Scanner status shows when each scanner sent its last results.', spot: 'lanes', wide: true },
    { shot: 'status', step: 3, caption: 'Go back to Findings.', spot: 'findingsLink', click: { box: 'findingsLink', to: 'findings2', page: true } },
    { shot: 'findings2', step: 3, caption: 'Open a Stale finding.', spot: 'row', wide: true, click: { box: 'row', to: 'finding', page: true } },
    { shot: 'finding', step: 3, caption: 'JAVV set this state, because the scanner is silent. A state that a person sets replaces it.', spot: 'note', hold: 'panel' },
    { shot: 'finding', step: 3, caption: 'The finding of each scanner is Stale, because both scanners are silent.', spot: 'evidenceState' },
  ],
}

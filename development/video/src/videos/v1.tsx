// Video 1: from a scan to a finding.
import { Easing, interpolate, spring } from 'remotion'
import shots from '../../public/v1/shots.json'
import { C, MONO, SANS, type Video } from '../engine'

const TRIVY = '#2f7d6d'
const GRYPE = '#6b5bb5'
const IMAGES = ['web-9:3.8.8', 'auth-5:2.4.6', 'billing-3:2.11.1', 'gateway-6:3.5.2', 'search-4:2.17.1', 'worker-2:3.3.4']
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const

// the intro captions, in frames from the start of the intro
const C1 = 150
const C2 = 120
const C3 = 160

/** the cluster, its images, the two scanners, and JAVV keeping their results apart */
function Diagram({ frame: f }: { frame: number }) {
  const fps = 30
  const box = spring({ frame: f - 4, fps, config: { damping: 200 } })
  const scanners = spring({ frame: f - 40, fps, config: { damping: 16 } })
  // a scan line passes over the images twice during the first caption
  const sweep = interpolate(f, [56, 140], [0, 2], clamp) % 1
  const sweepOn = f > 56 && f < 140
  const javv = spring({ frame: f - C1, fps, config: { damping: 200 } })
  const flow = f - C1 - 10
  const split = f - C1 - C2
  const rows = (n: number, start: number) => Math.max(0, Math.min(n, Math.floor((split - start) / 5)))
  const count = (to: number) => Math.round(interpolate(split, [10, 70], [0, to], { ...clamp, easing: Easing.out(Easing.cubic) }))

  const packets = (y0: number, color: string, delay: number) =>
    [0, 1, 2, 3].map((i) => {
      const t = (flow - delay - i * 9) / 34
      if (flow < 0 || t < 0 || t > 1) return null
      const x = interpolate(t, [0, 1], [640, 1000])
      const y = interpolate(t, [0, 1], [y0, 432])
      return <div key={i} style={{ position: 'absolute', left: x - 7, top: y - 7, width: 14, height: 14, borderRadius: 4, background: color }} />
    })

  return (
    <div style={{ position: 'absolute', inset: 0, background: C.bg, fontFamily: SANS }}>
      {/* the cluster */}
      <div
        style={{
          position: 'absolute', left: 80, top: 120, width: 560, height: 624, borderRadius: 22, background: C.card,
          boxShadow: '0 18px 50px rgb(22 35 47 / 12%)', border: `1px solid ${C.line}`, opacity: box, transform: `translateY(${(1 - box) * 30}px)`,
        }}
      >
        <div style={{ padding: '22px 28px', fontFamily: MONO, fontSize: 17, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgb(22 35 47 / 60%)' }}>
          Your cluster · prod-eu-1
        </div>
        <div style={{ position: 'absolute', left: 28, top: 76, right: 28, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          {IMAGES.map((img, i) => {
            const k = spring({ frame: f - 12 - i * 4, fps, config: { damping: 200 } })
            return (
              <div key={img} style={{ height: 66, borderRadius: 12, background: C.panel, border: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', gap: 12, padding: '0 16px', opacity: k, transform: `scale(${0.9 + k * 0.1})` }}>
                <div style={{ width: 26, height: 26, borderRadius: 7, background: C.slate2 }} />
                <span style={{ fontFamily: MONO, fontSize: 17, color: C.ink }}>{img}</span>
              </div>
            )
          })}
          {sweepOn ? (
            <div style={{ position: 'absolute', left: -8, right: -8, top: sweep * 236 - 4, height: 4, borderRadius: 2, background: C.coral, boxShadow: `0 0 18px ${C.coral}` }} />
          ) : null}
        </div>
        {[
          { name: 'Trivy', color: TRIVY, top: 360 },
          { name: 'Grype', color: GRYPE, top: 470 },
        ].map((s) => (
          <div
            key={s.name}
            style={{
              position: 'absolute', left: 28, right: 28, top: s.top, height: 88, borderRadius: 14, background: s.color, color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 24px',
              opacity: scanners, transform: `translateY(${(1 - scanners) * 24}px)`,
            }}
          >
            <span style={{ fontSize: 30, fontWeight: 700 }}>{s.name}</span>
            <span style={{ fontFamily: MONO, fontSize: 15, letterSpacing: '.08em', textTransform: 'uppercase', opacity: 0.85 }}>scanner</span>
          </div>
        ))}
      </div>

      {/* the results travelling to JAVV */}
      {packets(120 + 360 + 44, TRIVY, 0)}
      {packets(120 + 470 + 44, GRYPE, 5)}

      {/* JAVV */}
      <div
        style={{
          position: 'absolute', left: 1000, top: 120, width: 456, height: 624, borderRadius: 22, background: C.slate, color: '#fff',
          boxShadow: '0 18px 50px rgb(22 35 47 / 28%)', opacity: javv, transform: `translateX(${(1 - javv) * 40}px)`,
        }}
      >
        <div style={{ padding: '22px 28px', display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 34, fontWeight: 700, letterSpacing: '-.02em' }}>javv</span>
        </div>
        <div style={{ position: 'absolute', left: 28, right: 28, top: 92, bottom: 28, display: 'flex', gap: 0 }}>
          {[
            { name: 'trivy', color: TRIVY, n: 233, delay: 0 },
            { name: 'grype', color: GRYPE, n: 218, delay: 3 },
          ].map((s, i) => (
            <div key={s.name} style={{ flex: 1, padding: i ? '0 0 0 16px' : '0 16px 0 0', borderLeft: i ? '2px dashed rgb(255 255 255 / 30%)' : 'none' }}>
              <div style={{ display: 'inline-block', fontFamily: MONO, fontSize: 16, fontWeight: 700, padding: '4px 10px', borderRadius: 6, background: s.color }}>{s.name}</div>
              <div style={{ marginTop: 14, fontFamily: MONO, fontSize: 40, fontWeight: 700, opacity: split > 0 ? 1 : 0 }}>{count(s.n)}</div>
              <div style={{ fontFamily: MONO, fontSize: 14, opacity: split > 0 ? 0.7 : 0 }}>findings</div>
              <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
                {Array.from({ length: rows(9, s.delay) }).map((_, r) => (
                  <div key={r} style={{ height: 22, borderRadius: 5, background: 'rgb(255 255 255 / 12%)', borderLeft: `4px solid ${s.color}` }} />
                ))}
              </div>
            </div>
          ))}
        </div>
        <div
          style={{
            position: 'absolute', left: '50%', bottom: 40, transform: 'translateX(-50%)', padding: '8px 16px', borderRadius: 999,
            background: C.coral, color: C.slate, fontFamily: MONO, fontSize: 15, fontWeight: 700, letterSpacing: '.06em', textTransform: 'uppercase',
            opacity: interpolate(split, [60, 74], [0, 1], clamp), whiteSpace: 'nowrap',
          }}
        >
          never merged
        </div>
      </div>
    </div>
  )
}

export const v1: Video = {
  dir: 'v1',
  shots,
  title: 'From a scan to a finding',
  kicker: 'Triage · video 1 of 6',
  next: 'Next: set the state of a finding',
  steps: 4,
  intro: {
    component: Diagram,
    captions: [
      { step: 1, text: 'Trivy and Grype run in your cluster. They scan each running image.', frames: C1 },
      { step: 1, text: 'Each scanner sends its results to JAVV.', frames: C2 },
      { step: 1, text: 'JAVV keeps the results of each scanner separate. It never merges them.', frames: C3 },
    ],
  },
  beats: [
    { shot: 'clusters', step: 2, caption: 'All clusters shows each cluster that sends results to JAVV.', spot: 'table', wide: true },
    { shot: 'clusters', step: 2, caption: 'Select a cluster to open it.', spot: 'cluster', wide: true, click: { box: 'cluster', to: 'overview', page: true } },
    { shot: 'overview', step: 2, caption: 'Open Findings from the side menu.', spot: 'findingsLink', click: { box: 'findingsLink', to: 'findings', page: true } },
    { shot: 'findings', step: 3, caption: 'Each row is one finding: one CVE, in one package, in one image, from one scanner.', spot: 'row', wide: true },
    { shot: 'findings', step: 3, caption: 'Filter the findings by scanner here.', spot: 'scannerFacet' },
    { shot: 'findings', step: 3, caption: 'Select a finding to open it.', spot: 'row', wide: true, click: { box: 'row', to: 'finding', page: true } },
    { shot: 'finding', step: 4, caption: 'The evidence shows the result of each scanner, side by side.', spot: 'evidence' },
    { shot: 'finding', step: 4, caption: 'Set the state of the finding in the triage panel. The next video shows how.', spot: 'panel', hold: 'panel' },
  ],
}

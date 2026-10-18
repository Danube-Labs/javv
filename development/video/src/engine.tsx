// The shared engine of the triage videos: a window on the JAVV background, a camera over 2x
// screenshots, a spotlight, a pointer with click pulses, one caption pill, and the title and
// closing cards. A video is a `Video`: its shots, its words and its beats. All timing comes from
// the beats, so a video script has no frame numbers.
import { type ComponentType, useEffect, useState } from 'react'
import {
  AbsoluteFill,
  Easing,
  Img,
  continueRender,
  delayRender,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion'

// JAVV tokens (frontend/src/styles/tokens.css)
export const C = {
  bg: '#efeadf',
  ink: '#1b2935',
  slate: '#16232f',
  slate2: '#21384a',
  coral: '#ec7e54',
  coralText: '#a8481f',
  card: '#ffffff',
  panel: '#fbfaf6',
  line: '#e7e0d3',
}
export const SANS = "'Hanken Grotesk', sans-serif"
export const MONO = "'Spline Sans Mono', monospace"

type Box = { x: number; y: number; w: number; h: number }
export type Shot = { name: string; file: string; size: { w: number; h: number }; boxes: Record<string, Box> }
export type ShotSet = { view: { width: number; height: number }; shots: Shot[] }

export type Beat = {
  shot: string
  step: number
  caption: string
  spot?: string // a box of the shot to light; the camera frames it
  hold?: string // keep the camera on this box (a steady zoom over several beats); only the height follows the spot
  wide?: boolean // the camera shows the whole width of the page
  click?: {
    box: string
    to: string // the screen after the click
    page?: boolean // a new page: soft fade; else a quick switch
    via?: string[] // screens between the click and `to`, a few frames each (typing)
  }
}

/** a motion scene before the screens, drawn inside the window */
export type Intro = {
  component: ComponentType<{ frame: number }>
  captions: { step: number; text: string; frames: number }[]
}

export type Video = {
  dir: string // under public/
  shots: ShotSet
  title: string
  kicker: string
  next: string
  steps: number
  beats: Beat[]
  intro?: Intro
}

// the window and its screen: smaller than the frame, so the caption pill sits under it
const WIN = { x: 192, y: 26, w: 1536, bar: 36 }
const STAGE = { w: 1536, h: 864 }

// pacing (frames at 30 fps)
const TITLE_F = 78
const CAM_F = 34 // the camera move at the start of a beat; the spotlight waits for it
const SPOT_IN = 10
const GLIDE_F = 28
const HOVER_F = 12
const RESULT_F = 38 // the new screen stays, with no spotlight, before the next beat
const VIA_F = 7 // each in-between screen (typing)
const END_F = 84
const HOLD_W = 960 // the steady zoom for held beats, in page pixels
/** time to read a caption: about 3.5 words a second, plus time to find it on screen */
const readFrames = (text: string) => Math.min(150, Math.max(72, text.split(' ').length * 8 + 24))

const ease = Easing.bezier(0.65, 0, 0.35, 1)
const clamp = { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' } as const
const center = (b: Box) => ({ x: b.x + b.w / 2, y: b.y + b.h / 2 })

type Cam = { f: number; cx: number; cy: number; w: number }
type Point = { f: number; x: number; y: number }
export type Plan = {
  shots: Record<string, Shot>
  pageW: number
  segments: { shot: string; from: number; fade: number }[]
  camera: Cam[]
  pointer: Point[]
  clicks: number[]
  captions: { from: number; to: number; step: number; text: string }[]
  spots: { from: number; to: number; shot: string; box: string }[]
  introEnd: number
  end: number
  duration: number
}

export function plan(v: Video): Plan {
  const shots: Record<string, Shot> = Object.fromEntries(v.shots.shots.map((s) => [s.name, s]))
  const pageW = v.shots.view.width
  const p: Plan = { shots, pageW, segments: [], camera: [], pointer: [], clicks: [], captions: [], spots: [], introEnd: TITLE_F, end: 0, duration: 0 }

  const frameBox = (b: Box, pageH: number) => {
    const w = Math.min(pageW, Math.max(800, b.w / 0.55, ((b.h / 0.7) * STAGE.w) / STAGE.h))
    const h = (w * STAGE.h) / STAGE.w
    const c = center(b)
    return { cx: Math.min(pageW - w / 2, Math.max(w / 2, c.x)), cy: Math.min(pageH - h / 2, Math.max(h / 2, c.y)), w }
  }

  let t = TITLE_F
  if (v.intro) {
    for (const c of v.intro.captions) {
      p.captions.push({ from: t + 4, to: t + c.frames, step: c.step, text: c.text })
      t += c.frames
    }
    p.introEnd = t
    // the diagram fades out first, then the screen fades in: no frame shows both
    t += 12
  }
  const first = shots[v.beats[0].shot]
  let cam = { cx: pageW / 2, cy: (pageW * STAGE.h) / STAGE.w / 2, w: pageW }
  let ptr = { x: pageW * 0.82, y: first.size.h * 0.4 }
  p.segments.push({ shot: v.beats[0].shot, from: v.intro ? t + 10 : t, fade: v.intro ? 10 : 0 })
  // after an intro the first caption follows at once; after the title card the screen settles first
  const settleF = v.intro ? 0 : 24
  p.camera.push({ f: t, ...cam }, { f: t + settleF, ...cam })
  p.pointer.push({ f: t + Math.max(settleF, 12), ...ptr })
  t += settleF
  for (const b of v.beats) {
    const shot = shots[b.shot]
    let next = b.spot ? frameBox(shot.boxes[b.spot], shot.size.h) : cam
    if (b.hold) {
      const hb = shot.boxes[b.hold]
      const h = (HOLD_W * STAGE.h) / STAGE.w
      const sy = b.spot ? center(shot.boxes[b.spot]).y : center(hb).y
      next = { w: HOLD_W, cx: Math.min(pageW - HOLD_W / 2, Math.max(HOLD_W / 2, center(hb).x - 40)), cy: Math.min(shot.size.h - h / 2, Math.max(h / 2, sy)) }
    }
    if (b.wide) {
      const h = (pageW * STAGE.h) / STAGE.w
      const sy = b.spot ? center(shot.boxes[b.spot]).y : h / 2
      next = { w: pageW, cx: pageW / 2, cy: Math.min(shot.size.h - h / 2, Math.max(h / 2, sy)) }
    }
    p.camera.push({ f: t, ...cam }, { f: t + CAM_F, ...next })
    cam = next
    const read = readFrames(b.caption)
    const capFrom = t + 4
    const spotFrom = t + CAM_F
    let end: number
    let spotTo: number
    if (b.click) {
      const act = Math.max(capFrom + read, spotFrom + 30)
      const target = center(shot.boxes[b.click.box])
      p.pointer.push({ f: act, ...ptr }, { f: act + GLIDE_F, ...target })
      const hover = act + GLIDE_F
      if (shots[`${b.shot}-hover`]) p.segments.push({ shot: `${b.shot}-hover`, from: hover, fade: 4 })
      const press = hover + HOVER_F
      p.clicks.push(press)
      const away = { x: target.x + 90, y: target.y + 70 }
      p.pointer.push({ f: press + 6, ...target }, { f: press + 30, ...away })
      ptr = away
      // the spotlight leaves at the press: the screen changes under it
      spotTo = press
      let s = press + 6
      for (const via of b.click.via ?? []) {
        p.segments.push({ shot: via, from: s, fade: 0 })
        s += VIA_F
      }
      // a new page fades in; a change inside the page switches fast, as in the app: a slow
      // crossfade between two layouts that shifted shows a double image
      p.segments.push({ shot: b.click.to, from: s, fade: b.click.page ? 10 : 3 })
      end = Math.max(s, press + 30) + RESULT_F
    } else {
      end = Math.max(capFrom + read, spotFrom + 40) + 14
      spotTo = end - 6
    }
    p.pointer.push({ f: end, ...ptr })
    p.captions.push({ from: capFrom, to: end, step: b.step, text: b.caption })
    if (b.spot) p.spots.push({ from: spotFrom, to: spotTo, shot: b.shot, box: b.spot })
    t = end
  }
  p.camera.push({ f: t + END_F, ...cam })
  p.end = t
  p.duration = t + END_F
  return p
}

function keyed<T extends { f: number }>(keys: T[], f: number, pick: (k: T) => number) {
  if (f <= keys[0].f) return pick(keys[0])
  for (let i = 1; i < keys.length; i++) {
    if (f <= keys[i].f) {
      const a = keys[i - 1], b = keys[i]
      if (b.f === a.f) return pick(b)
      return interpolate(f, [a.f, b.f], [pick(a), pick(b)], { easing: ease })
    }
  }
  return pick(keys[keys.length - 1])
}

function useFonts() {
  const [handle] = useState(() => delayRender('fonts'))
  useEffect(() => {
    const faces = [
      ['Hanken Grotesk', 'hanken-grotesk-latin-400-normal', '400'],
      ['Hanken Grotesk', 'hanken-grotesk-latin-500-normal', '500'],
      ['Hanken Grotesk', 'hanken-grotesk-latin-600-normal', '600'],
      ['Hanken Grotesk', 'hanken-grotesk-latin-700-normal', '700'],
      ['Spline Sans Mono', 'spline-sans-mono-latin-400-normal', '400'],
      ['Spline Sans Mono', 'spline-sans-mono-latin-700-normal', '700'],
    ].map(([fam, file, weight]) => new FontFace(fam, `url(${staticFile(`fonts/${file}.woff2`)})`, { weight }))
    Promise.all(faces.map((f) => f.load())).then((loaded) => {
      loaded.forEach((f) => document.fonts.add(f))
      continueRender(handle)
    })
  }, [handle])
}

/** the page under the camera: screenshots, spotlight, pointer and click pulses */
function Screen({ p, dir }: { p: Plan; dir: string }) {
  const f = useCurrentFrame()
  if (f < p.segments[0].from - p.segments[0].fade) return null
  const cam = { cx: keyed(p.camera, f, (k) => k.cx), cy: keyed(p.camera, f, (k) => k.cy), w: keyed(p.camera, f, (k) => k.w) }
  const s = STAGE.w / cam.w
  const left = cam.cx - cam.w / 2
  const top = cam.cy - (cam.w * STAGE.h) / STAGE.w / 2
  const toStage = (x: number, y: number) => ({ x: (x - left) * s, y: (y - top) * s })

  const layers = p.segments.map((seg, i) => {
    const next = p.segments[i + 1]
    const fadeIn = seg.fade ? interpolate(f, [seg.from - seg.fade, seg.from], [0, 1], clamp) : f >= seg.from ? 1 : 0
    const gone = next && f >= next.from + 2 ? 0 : 1
    return { seg, opacity: fadeIn * gone }
  })

  const ptr = toStage(keyed(p.pointer, f, (k) => k.x), keyed(p.pointer, f, (k) => k.y))
  const pointerOn = interpolate(f, [p.pointer[0].f - 10, p.pointer[0].f, p.end, p.end + 14], [0, 1, 1, 0], clamp)
  const pressing = p.clicks.some((c) => f >= c - 3 && f <= c + 4)

  const spot = p.spots.find((sp) => f >= sp.from && f <= sp.to + 8)
  let spotEl = null
  if (spot) {
    const b = p.shots[spot.shot].boxes[spot.box]
    const pad = 6
    const a = toStage(b.x - pad, b.y - pad)
    const w = (b.w + pad * 2) * s
    const h = (b.h + pad * 2) * s
    const o = interpolate(f, [spot.from, spot.from + SPOT_IN, spot.to, spot.to + 8], [0, 1, 1, 0], clamp)
    const grow = interpolate(f, [spot.from, spot.from + SPOT_IN + 4], [10, 0], { easing: Easing.out(Easing.cubic), ...clamp })
    spotEl = (
      <svg width={STAGE.w} height={STAGE.h} style={{ position: 'absolute', inset: 0, opacity: o }}>
        <defs>
          <mask id="hole">
            <rect width="100%" height="100%" fill="white" />
            <rect x={a.x - grow} y={a.y - grow} width={w + grow * 2} height={h + grow * 2} rx={12} fill="black" />
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgb(22 35 47 / 42%)" mask="url(#hole)" />
        <rect x={a.x - grow} y={a.y - grow} width={w + grow * 2} height={h + grow * 2} rx={12} fill="none" stroke={C.coral} strokeWidth={3} />
      </svg>
    )
  }

  return (
    <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
      {layers.map(({ seg, opacity }, i) =>
        opacity > 0 ? (
          <Img
            key={`${seg.shot}-${i}`}
            src={staticFile(`${dir}/${p.shots[seg.shot].file}`)}
            style={{ position: 'absolute', left: -left * s, top: -top * s, width: p.pageW * s, opacity }}
          />
        ) : null,
      )}
      {spotEl}
      {p.clicks.map((c) => {
        const t = f - c
        if (t < 0 || t > 22) return null
        const q = toStage(keyed(p.pointer, c, (k) => k.x), keyed(p.pointer, c, (k) => k.y))
        const r = interpolate(t, [0, 22], [8, 54], { easing: Easing.out(Easing.cubic) })
        return (
          <div
            key={c}
            style={{
              position: 'absolute', left: q.x - r, top: q.y - r, width: r * 2, height: r * 2, borderRadius: '50%',
              border: `3px solid ${C.coral}`, opacity: interpolate(t, [0, 22], [0.95, 0]),
            }}
          />
        )
      })}
      <div
        style={{
          position: 'absolute', left: ptr.x - 13, top: ptr.y - 13, width: 26, height: 26, borderRadius: '50%',
          background: 'rgb(236 126 84 / 55%)', border: `3px solid ${C.coral}`, boxShadow: '0 0 0 5px rgb(236 126 84 / 18%)',
          opacity: pointerOn, transform: `scale(${pressing ? 0.76 : 1})`,
        }}
      />
    </div>
  )
}

/** the dark floating pill: it stays for the whole walk; the step and the text change inside it */
function Caption({ p, steps }: { p: Plan; steps: number }) {
  const f = useCurrentFrame()
  const { fps } = useVideoConfig()
  const caps = p.captions
  const first = caps[0].from
  const last = caps[caps.length - 1].to
  if (f < first || f > last + 12) return null
  const enter = spring({ frame: f - first, fps, config: { damping: 200 }, durationInFrames: 16 })
  const leave = interpolate(f, [last, last + 12], [1, 0], clamp)
  const found = caps.findIndex((c) => f < c.to)
  const i = found === -1 ? caps.length - 1 : found
  const cap = caps[i]
  // the old text fades out just before the new one rises in
  const kIn = i === 0 ? 1 : spring({ frame: f - cap.from, fps, config: { damping: 200 }, durationInFrames: 12 })
  const kOut = i === caps.length - 1 ? 1 : interpolate(f, [cap.to - 6, cap.to], [1, 0], clamp)
  const k = kIn * kOut
  return (
    <div style={{ position: 'absolute', left: 0, right: 0, bottom: 40, display: 'flex', justifyContent: 'center' }}>
      <div
        style={{
          width: 1360, height: 84, padding: '0 32px 0 26px', borderRadius: 18, boxSizing: 'border-box',
          background: 'rgb(22 35 47 / 95%)', boxShadow: '0 18px 50px rgb(22 35 47 / 32%)', display: 'flex', alignItems: 'center', gap: 20,
          opacity: enter * leave, transform: `translateY(${(1 - enter) * 26}px)`,
        }}
      >
        <div style={{ width: 44, fontFamily: MONO, fontSize: 19, fontWeight: 700, color: C.coral, letterSpacing: '.06em', whiteSpace: 'nowrap' }}>
          {cap.step}/{steps}
        </div>
        <div style={{ width: 2, height: 40, background: 'rgb(255 255 255 / 18%)' }} />
        <div style={{ fontFamily: SANS, fontSize: cap.text.length > 66 ? 26 : 30, lineHeight: 1.2, fontWeight: 600, color: '#fff', opacity: k, transform: `translateY(${(1 - k) * 10}px)` }}>
          {cap.text}
        </div>
      </div>
    </div>
  )
}

/** a full-frame card with the mark: the title at the start, what comes next at the end */
function Card({ from, to, title, kicker, fadeIn }: { from: number; to: number; title: string; kicker: string; fadeIn: boolean }) {
  const f = useCurrentFrame()
  const { fps } = useVideoConfig()
  if (f < from || f > to) return null
  const local = f - from
  const mark = spring({ frame: local - 2, fps, config: { damping: 14, mass: 0.7 } })
  const opacity = fadeIn ? interpolate(f, [from, from + 10], [0, 1], clamp) : interpolate(f, [to - 14, to], [1, 0], clamp)
  const words = title.split(' ')
  return (
    <AbsoluteFill style={{ background: C.bg, alignItems: 'center', justifyContent: 'center', opacity }}>
      <div style={{ textAlign: 'center', transform: `translateY(${interpolate(f, [to - 14, to], [0, -30], clamp)}px)` }}>
        <Img src={staticFile('icon.svg')} style={{ width: 92, height: 92, transform: `scale(${mark}) rotate(${(1 - mark) * -40}deg)` }} />
        <div style={{ marginTop: 26, fontFamily: SANS, fontSize: 64, fontWeight: 700, letterSpacing: '-.02em', color: C.ink }}>
          {words.map((w, i) => {
            const k = spring({ frame: local - 10 - i * 3, fps, config: { damping: 200 } })
            return (
              <span key={i} style={{ opacity: k, transform: `translateY(${(1 - k) * 36}px)`, display: 'inline-block', marginRight: '0.28em' }}>
                {w}
              </span>
            )
          })}
        </div>
        <div style={{ marginTop: 16, fontFamily: MONO, fontSize: 20, fontWeight: 700, letterSpacing: '.12em', textTransform: 'uppercase', color: C.coralText, opacity: interpolate(local, [24, 38], [0, 1], clamp) }}>
          {kicker}
        </div>
      </div>
    </AbsoluteFill>
  )
}

export function makeVideo(v: Video) {
  const p = plan(v)
  const Component = () => {
    useFonts()
    const f = useCurrentFrame()
    const { fps } = useVideoConfig()
    const rise = spring({ frame: f - TITLE_F, fps, config: { damping: 200 }, durationInFrames: 24 })
    const Intro = v.intro?.component
    const introOut = interpolate(f, [p.introEnd - 8, p.introEnd + 4], [1, 0], clamp)
    return (
      <AbsoluteFill style={{ background: `radial-gradient(1200px 700px at 30% 20%, #f6f2ea, ${C.bg})` }}>
        <div
          style={{
            position: 'absolute', left: WIN.x, top: WIN.y, width: WIN.w, height: STAGE.h + WIN.bar, borderRadius: 16, overflow: 'hidden', background: C.card,
            boxShadow: '0 30px 80px rgb(22 35 47 / 22%), 0 0 0 1px rgb(22 35 47 / 8%)',
            opacity: rise, transform: `translateY(${(1 - rise) * 70}px) scale(${0.94 + rise * 0.06})`,
          }}
        >
          <div style={{ height: WIN.bar, background: '#f7f4ee', borderBottom: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', gap: 8, padding: '0 16px' }}>
            {['#e6a091', '#e8cf8f', '#a9c9a0'].map((c) => (
              <div key={c} style={{ width: 12, height: 12, borderRadius: '50%', background: c }} />
            ))}
            <div style={{ marginLeft: 18, fontFamily: MONO, fontSize: 14, color: 'rgb(22 35 47 / 50%)' }}>javv.example</div>
          </div>
          <div style={{ position: 'absolute', left: 0, top: WIN.bar, width: STAGE.w, height: STAGE.h, background: C.bg }}>
            <Screen p={p} dir={v.dir} />
            {Intro && f < p.introEnd + 12 ? (
              <div style={{ position: 'absolute', inset: 0, opacity: introOut }}>
                <Intro frame={f - TITLE_F} />
              </div>
            ) : null}
          </div>
        </div>
        <Caption p={p} steps={v.steps} />
        <Card from={0} to={TITLE_F} title={v.title} kicker={v.kicker} fadeIn={false} />
        <Card from={p.end + 6} to={p.duration} title={v.next} kicker="JAVV triage" fadeIn />
      </AbsoluteFill>
    )
  }
  return { Component, duration: p.duration }
}

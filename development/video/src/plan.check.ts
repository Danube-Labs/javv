// Checks the spotlight of each video before render.sh renders it (operator ruling D1 of issue
// 1220): the spotlight lights only its own screen, no other screen starts to show while it is
// there, and it stays at most 2.5 s. render.sh stops on a failure.
import { plan, type Plan } from './engine'
import { v1 } from './videos/v1'
import { v2 } from './videos/v2'
import { v3 } from './videos/v3'
import { v4 } from './videos/v4'
import { v5 } from './videos/v5'
import { v6 } from './videos/v6'
import { v7 } from './videos/v7'

const FPS = 30
const SPOT_MAX = 2.5 * FPS

/** the screen that is drawn on top at frame f: the last one that started to fade in */
function shownAt(p: Plan, f: number) {
  let shot = p.segments[0].shot
  for (const s of p.segments) if (s.from - s.fade <= f) shot = s.shot
  return shot
}

export function spotProblems(name: string, p: Plan): string[] {
  const out: string[] = []
  const at = (f: number) => `${name} ${(f / FPS).toFixed(2)} s`
  for (const sp of p.spots) {
    if (sp.to - sp.from > SPOT_MAX) out.push(`${at(sp.from)}: the spotlight on ${sp.box} stays ${((sp.to - sp.from) / FPS).toFixed(1)} s`)
    for (let f = sp.from; f <= sp.to; f++) {
      const shown = shownAt(p, f)
      if (shown !== sp.shot && shown !== `${sp.shot}-hover`) {
        out.push(`${at(f)}: the spotlight on ${sp.shot}/${sp.box} is over the screen ${shown}`)
        break
      }
    }
  }
  return out
}

const problems = Object.entries({ v1, v2, v3, v4, v5, v6, v7 }).flatMap(([name, v]) => spotProblems(name, plan(v)))
for (const line of problems) process.stderr.write(`${line}\n`)
process.stderr.write(`plan check: ${problems.length} problem(s)\n`)
process.exitCode = problems.length ? 1 : 0

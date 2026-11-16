/** The declarations of one selector in the style block of a component, read from its source. */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** `file` is a path under `src/`; returns `{ property: value }` of each rule that lists `selector`. */
export function declarations(file: string, selector: string): Record<string, string> {
  const source = readFileSync(resolve(process.cwd(), 'src', file), 'utf8')
  const css = (/<style[^>]*>([\s\S]*?)<\/style>/.exec(source)?.[1] ?? '').replace(/\/\*[\s\S]*?\*\//g, '')
  const out: Record<string, string> = {}
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (!(m[1] ?? '').split(',').map((s) => s.trim()).includes(selector)) continue
    for (const d of (m[2] ?? '').split(';')) {
      const [k, ...v] = d.split(':')
      if (k?.trim()) out[k.trim()] = v.join(':').trim()
    }
  }
  return out
}

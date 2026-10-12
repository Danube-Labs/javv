/**
 * The app loads nothing from another origin (issue 818): behind a firewall that drops outside
 * traffic, one outside stylesheet held the sign-in page blank for 21.8 s. So the fonts are served
 * by the app, and these checks keep both halves true: index.html names no outside origin, and
 * every family the tokens use has a face that the app itself ships.
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const read = (path: string) => readFileSync(resolve(process.cwd(), path), 'utf8')
const html = read('index.html')
const tokens = read('src/styles/tokens.css')
const fonts = read('src/styles/fonts.css')
const main = read('src/main.ts')
const pkg = JSON.parse(read('package.json')) as { dependencies: Record<string, string> }

const familyOf = (token: string) => tokens.match(new RegExp(`--${token}:\\s*'([^']+)'`))![1]
const faces = [...fonts.matchAll(/@font-face\s*\{([^}]*)\}/g)].map((m) => m[1]!).map((body) => ({
  family: body.match(/font-family:\s*'([^']+)'/)![1],
  weight: Number(body.match(/font-weight:\s*(\d+)/)![1]),
  src: body.match(/src:\s*([^;]+);/)![1]!,
  range: body.match(/unicode-range:\s*([^;]+);/)?.[1],
}))

describe('index.html', () => {
  it('names no outside origin', () => {
    expect(html).not.toMatch(/https?:\/\//i)
    expect(html).not.toMatch(/(src|href)\s*=\s*["']\/\//i)
    expect(html).not.toMatch(/rel=["']?(preconnect|dns-prefetch|preload)/i)
  })
})

describe('src/styles/fonts.css', () => {
  it('is loaded by the app entry before the tokens', () => {
    expect(main.indexOf("import './styles/fonts.css'")).toBeGreaterThanOrEqual(0)
    expect(main.indexOf("import './styles/fonts.css'")).toBeLessThan(main.indexOf("import './styles/tokens.css'"))
  })

  it.each([
    ['font-ui', [400, 500, 600, 700]],
    ['font-mono', [400, 700]],
  ])('ships a latin and a latin-ext face for every weight of --%s', (token, weights) => {
    const family = familyOf(token)
    for (const weight of weights) {
      const subsets = faces
        .filter((f) => f.family === family && f.weight === weight)
        .map((f) => f.src.match(/-(latin(?:-ext)?)-\d+-normal\.woff2/)![1])
      expect(subsets.sort(), `${family} ${weight}`).toEqual(['latin', 'latin-ext'])
    }
  })

  it('gives every face a unicode-range, so a subset never shadows the other', () => {
    expect(faces.length).toBeGreaterThan(0)
    expect(faces.filter((f) => !f.range)).toEqual([])
  })

  it('serves every face from a Fontsource package the app depends on', () => {
    const shipped = /^url\('(@fontsource\/[^/]+)\/files\/[^']+\.woff2'\) format\('woff2'\)$/
    for (const { src } of faces) {
      expect(src).toMatch(shipped)
      expect(Object.keys(pkg.dependencies)).toContain(src.match(shipped)![1])
    }
  })
})

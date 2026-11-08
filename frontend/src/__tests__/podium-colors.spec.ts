/**
 * Contributors: first place on the podium and the "SLA met" dot are slate, not coral. Coral is in
 * the red-orange of critical, so it read as a severity there (issue 1140, R8). The coral hover line
 * of a card stays, as on every clickable card (issue 1004).
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const read = (path: string) => readFileSync(join(__dirname, '..', path), 'utf8')
function rule(css: string, selector: string): string {
  const at = css.indexOf(`\n${selector} {`)
  expect(at, `${selector} is in the CSS`).toBeGreaterThan(-1)
  return css.slice(at, css.indexOf('}', at))
}

describe('the slate accent of Contributors', () => {
  const podium = read('components/contributors/PodiumCard.vue')

  it('first place has the slate line and the slate badge', () => {
    expect(rule(podium, '.podium-first')).toContain('border-color: var(--slate2);')
    expect(rule(podium, '.podium-first .podium-rank')).toContain('background: var(--slate2);')
  })

  it('the hover line of a podium card stays coral', () => {
    expect(rule(podium, '.podium:hover')).toContain('border-color: var(--coral);')
  })

  it('the dot of SLA met is slate', () => {
    expect(read('views/ContributorsView.vue')).toContain(
      '<i class="stat-dot" style="background: var(--slate2)" />SLA met',
    )
  })
})

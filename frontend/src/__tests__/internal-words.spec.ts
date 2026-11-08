/**
 * Two head notes said how the app is built, not what a user sees (issue 1152): Running images
 * said "digest-deduped", and the OpenSearch runtime card said "deploy-owned (GitOps)".
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const template = (path: string) =>
  readFileSync(join(__dirname, '..', path), 'utf8').split('<template>')[1]!.replace(/\s+/g, ' ')

describe('internal words in head notes', () => {
  it('Running images says one row for each image digest', () => {
    const src = template('views/ImagesView.vue')
    expect(src).toContain('</template>one row for each image digest </p>')
    expect(src).not.toContain('deduped')
  })

  it('the OpenSearch runtime card says who sets its settings', () => {
    const src = template('components/settings/OpensearchRuntimeCard.vue')
    expect(src).toContain(
      'subtitle="read-only: the install of JAVV sets these settings, and the card shows each one that it can read"',
    )
    expect(src).not.toMatch(/GitOps|deploy-owned|displayable/)
  })
})

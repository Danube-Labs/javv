/**
 * Settings › Scan scope says how a scan finds the running images, in words that are true for each
 * source of scans: the JAVV scanners in Kubernetes, the Nomad jobs and the Docker containers
 * (issue 1152).
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const template = readFileSync(join(__dirname, '..', 'views/settings/ScanScopeView.vue'), 'utf8').split(
  '<template>',
)[1]!

describe('the words of Scan scope', () => {
  it('the row Running workloads only names each source of scans', () => {
    const row = template.split('label="Running workloads only"')[1]!.split('>')[0]!
    expect(row.replace(/\s+/g, ' ')).toContain(
      'hint="Only running images are scanned. The scanner lists what runs now: the pods in ' +
        'Kubernetes, the allocations in Nomad or the containers of a Docker host. It scans each ' +
        'image digest once, however many copies run it."',
    )
    expect(row).not.toContain('Kubernetes API')
  })
})

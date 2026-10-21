/**
 * Saved-view capture ⇄ apply (M9f slice 4) — the SCREENS §6 deep-link contract as a GOLDEN
 * round-trip: workbench state → stored preset → /findings route query → the exact API query
 * body. Drift anywhere in the chain breaks every stored view silently; the golden pins it.
 */
import { describe, expect, it } from 'vitest'

import { buildFilterQuery } from '@/filters/buildFilterQuery'
import { emptySelections, FINDINGS_FIELDS } from '@/filters/fields.config'
import {
  captureLens,
  facetsTotal,
  presetCountQuery,
  presetSummary,
  presetToRouteQuery,
} from '@/findings/savedViews'
import { makeFiltersStore } from '@/stores/filters'
import { createPinia, setActivePinia } from 'pinia'

const CID = 'fcbcbe84-9da1-41fb-879e-83c3e0f995f0'

/** THE golden workbench: negated severity + included namespace + two flags + search text. */
const SELECTIONS = {
  ...emptySelections(FINDINGS_FIELDS),
  severity: ['low', 'negligible'],
  namespace: ['payments'],
  attr: ['kev', 'new'],
  q: ['curl'],
}
const MODES = { severity: 'not' } as const

const GOLDEN_PRESET = {
  exclude_severity: ['low', 'negligible'],
  namespace: ['payments'],
  kev: true,
  new_within_days: 7,
  q: 'curl',
}

const GOLDEN_ROUTE_QUERY = {
  q: 'curl',
  severity: '!low,!negligible',
  attr: 'kev,new',
  namespace: 'payments',
}

describe('saved views — the golden capture ⇄ apply round-trip (SCREENS §6)', () => {
  it('capture: workbench state → the stored preset (param-keyed, exclude family included)', () => {
    expect(captureLens(FINDINGS_FIELDS, SELECTIONS, MODES, 6.3)).toEqual(GOLDEN_PRESET)
  })

  it('apply: stored preset → the /findings route query (field-keyed, ! grammar)', () => {
    expect(presetToRouteQuery(FINDINGS_FIELDS, GOLDEN_PRESET as never)).toEqual(GOLDEN_ROUTE_QUERY)
  })

  it('round-trip: the applied URL re-emits the preset params EXACTLY (deep-link contract)', () => {
    setActivePinia(createPinia())
    const store = makeFiltersStore('golden-roundtrip', FINDINGS_FIELDS)()
    store.fromQuery(GOLDEN_ROUTE_QUERY)
    const body = buildFilterQuery(
      FINDINGS_FIELDS,
      store.selections,
      { cluster_id: CID, window_days: 6.3 },
      store.modes,
    )
    expect(body).toEqual({ cluster_id: CID, ...GOLDEN_PRESET })
  })

  it('card count query = preset params verbatim + tenant (facets — a size-0 agg, no PIT)', () => {
    expect(presetCountQuery(GOLDEN_PRESET as never, CID)).toEqual({
      cluster_id: CID,
      fields: ['severity'], // the one facet facetsTotal sums
      ...GOLDEN_PRESET,
    })
    expect(presetCountQuery({} as never, CID, '2026-07-01T00:00:00Z').as_of).toBe(
      '2026-07-01T00:00:00Z',
    )
  })

  it('facetsTotal sums the severity buckets — one severity per row makes it the lens total', () => {
    expect(facetsTotal({ facets: { severity: [{ count: 3 }, { count: 4 }] } })).toBe(7)
    expect(facetsTotal({ facets: { severity: [] } })).toBe(0)
    expect(facetsTotal({ facets: {} })).toBeNull()
    expect(facetsTotal({})).toBeNull()
    expect(facetsTotal(null)).toBeNull()
  })

  it('summary speaks the pill grammar, negation first-class', () => {
    const s = presetSummary(FINDINGS_FIELDS, GOLDEN_PRESET as never)
    expect(s).toContain('Severity is none of low, negligible')
    expect(s).toContain('Namespace is payments')
    expect(s).toContain('KEV')
    expect(presetSummary(FINDINGS_FIELDS, {} as never)).toBe('No filters: everything')
  })

  it('an empty workbench captures an empty preset — "everything" is a valid view', () => {
    expect(captureLens(FINDINGS_FIELDS, emptySelections(FINDINGS_FIELDS), {}, 30)).toEqual({})
  })
})

/**
 * Issue 949: namespace, package type and assignee are lists in a preset. A view saved before
 * that holds a plain string. The API sends the stored document as it is, so the frontend must
 * still read such a view, and its card count must still send a valid query.
 */
describe('saved views — several values in one field (issue 949)', () => {
  const MULTI = {
    ...emptySelections(FINDINGS_FIELDS),
    namespace: ['payments', 'edge'],
    ptype: ['debian', 'npm'],
    assignee: ['ana'],
  }

  it('capture and apply keep every value, in both modes', () => {
    const preset = captureLens(FINDINGS_FIELDS, MULTI, { ptype: 'not' }, 30)
    expect(preset).toEqual({
      namespace: ['payments', 'edge'],
      exclude_ptype: ['debian', 'npm'],
      assignee: ['ana'],
    })
    expect(presetToRouteQuery(FINDINGS_FIELDS, preset as never)).toEqual({
      namespace: 'payments,edge',
      ptype: '!debian,!npm',
      assignee: 'ana',
    })
    expect(presetSummary(FINDINGS_FIELDS, preset as never)).toContain('Namespace is one of payments, edge')
  })

  it('a view saved before issue 949, with one string value, still applies and counts', () => {
    const old = { namespace: 'payments', exclude_assignee: 'bob' }
    expect(presetToRouteQuery(FINDINGS_FIELDS, old as never)).toEqual({
      namespace: 'payments',
      assignee: '!bob',
    })
    expect(presetSummary(FINDINGS_FIELDS, old as never)).toContain('Namespace is payments')
    // the card count sends the stored value as it is: one value is a valid list param
    expect(presetCountQuery(old as never, CID)).toEqual({
      cluster_id: CID,
      fields: ['severity'],
      ...old,
    })
  })

  it('an empty stored list is no filter: no empty pill, no "Namespace is" on the card', () => {
    const empty = { namespace: [], exclude_ptype: [], assignee: ['ana'] }
    expect(presetToRouteQuery(FINDINGS_FIELDS, empty as never)).toEqual({ assignee: 'ana' })
    expect(presetSummary(FINDINGS_FIELDS, empty as never)).toBe('Assignee is ana')
    // an empty exclude list falls back to the include list of the same field
    expect(
      presetToRouteQuery(FINDINGS_FIELDS, { exclude_namespace: [], namespace: ['edge'] } as never),
    ).toEqual({ namespace: 'edge' })
  })
})

/**
 * A negated TEXT field (issue 349 §2): `image` is the one text field with an exclude twin
 * (`image_repo` is an exact `term` server-side). Same golden discipline — a preset that
 * captures `exclude_image_repo` but restores it as an include would misfilter under a pill
 * that reads correctly.
 */
describe('saved views — negated text field round-trip', () => {
  const REPO = 'docker.io/library/nginx'
  const SEL = { ...emptySelections(FINDINGS_FIELDS), image: [REPO] }
  const NOT_IMAGE = { image: 'not' } as const

  it('capture: a negated text selection lands on the exclude param', () => {
    expect(captureLens(FINDINGS_FIELDS, SEL, NOT_IMAGE, 30)).toEqual({ exclude_image_repo: REPO })
    // and the include side still captures plain — the mode is what flips it
    expect(captureLens(FINDINGS_FIELDS, SEL, {}, 30)).toEqual({ image_repo: REPO })
  })

  it('apply: exclude_image_repo restores through the same ! grammar as a terms field', () => {
    expect(presetToRouteQuery(FINDINGS_FIELDS, { exclude_image_repo: REPO } as never)).toEqual({
      image: `!${REPO}`,
    })
  })

  it('round-trip: the applied URL re-emits exclude_image_repo EXACTLY', () => {
    setActivePinia(createPinia())
    const store = makeFiltersStore('golden-text-not', FINDINGS_FIELDS)()
    store.fromQuery({ image: `!${REPO}` })
    const body = buildFilterQuery(FINDINGS_FIELDS, store.selections, { cluster_id: CID }, store.modes)
    expect(body).toEqual({ cluster_id: CID, exclude_image_repo: REPO })
  })

  it('summary speaks the negation, not just the value', () => {
    expect(presetSummary(FINDINGS_FIELDS, { exclude_image_repo: REPO } as never)).toBe(
      `Image is not "${REPO}"`,
    )
  })
})

/**
 * Issue 492: `cve` and `package` are the last two fields to join the family. They are
 * config-driven end to end — capture, apply and summary needed no code of their own — so the
 * round-trip is asserted rather than assumed, the same golden discipline as `image` above.
 */
describe('saved views — cve + package round-trip (issue 492)', () => {
  const CVE = 'CVE-2021-3711'
  const PKG = 'zlib'
  const SEL = { ...emptySelections(FINDINGS_FIELDS), cve: [CVE], package: [PKG] }

  it('capture: both directions land on the right params', () => {
    expect(captureLens(FINDINGS_FIELDS, SEL, {}, 30)).toEqual({ cve_id: CVE, package_name: PKG })
    expect(captureLens(FINDINGS_FIELDS, SEL, { cve: 'not', package: 'not' }, 30)).toEqual({
      exclude_cve_id: CVE,
      exclude_package_name: PKG,
    })
  })

  it('apply: the exclude params restore through the same ! grammar', () => {
    expect(
      presetToRouteQuery(FINDINGS_FIELDS, {
        exclude_cve_id: CVE,
        exclude_package_name: PKG,
      } as never),
    ).toEqual({ cve: `!${CVE}`, package: `!${PKG}` })
  })

  it('round-trip: the applied URL re-emits both exclude params EXACTLY', () => {
    setActivePinia(createPinia())
    const store = makeFiltersStore('golden-492', FINDINGS_FIELDS)()
    store.fromQuery({ cve: `!${CVE}`, package: `!${PKG}` })
    const body = buildFilterQuery(FINDINGS_FIELDS, store.selections, { cluster_id: CID }, store.modes)
    expect(body).toEqual({
      cluster_id: CID,
      exclude_cve_id: CVE,
      exclude_package_name: PKG,
    })
  })

  it('summary names the field a human recognises, not the param', () => {
    expect(presetSummary(FINDINGS_FIELDS, { exclude_package_name: PKG } as never)).toBe(
      `Package is not "${PKG}"`,
    )
  })
})

describe('saved views — the stored text filters are one-value lists (issue 949)', () => {
  // the server reads the one string the screen sends as a list and stores the list; a view
  // read back must apply and describe the same filter the user saved
  const STORED = { image_repo: ['registry.local/api'], exclude_cve_id: ['CVE-2021-3711'] }

  it('apply: a stored one-value list restores the text filter', () => {
    expect(presetToRouteQuery(FINDINGS_FIELDS, STORED as never)).toEqual({
      image: 'registry.local/api',
      cve: '!CVE-2021-3711',
    })
    expect(
      presetToRouteQuery(FINDINGS_FIELDS, { exclude_package_name: ['zlib'] } as never),
    ).toEqual({ package: '!zlib' })
  })

  it('summary: the card names the stored text filters', () => {
    expect(presetSummary(FINDINGS_FIELDS, STORED as never)).toBe(
      'Image "registry.local/api" · CVE is not "CVE-2021-3711"',
    )
  })

  it('an empty stored list is no filter', () => {
    expect(presetToRouteQuery(FINDINGS_FIELDS, { image_repo: [] } as never)).toEqual({})
  })
})

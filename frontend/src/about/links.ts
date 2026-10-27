/**
 * The About page's links (issue 341): operator docs in the repo, read on `main` because an upgrade
 * guide is read for the version you move TO. The versioned docs site replaces these once issue
 * 639 lands, and the live API reference (`/docs`) joins once issue 452 routes it. The repo moves
 * to `javv` after 1.0: this constant is the one line that changes.
 */
export const REPO_URL = 'https://github.com/Danube-Labs/javv'

export interface AboutLink {
  title: string
  hint: string
  href: string
}

const onMain = (path: string) => `${REPO_URL}/blob/main/${path}`

export const ABOUT_LINKS: AboutLink[] = [
  {
    title: 'Upgrading JAVV',
    hint: 'the order to upgrade in, what to check, and how to roll back',
    href: onMain('docs/UPGRADING.md'),
  },
  {
    title: 'Verify the signed images',
    hint: 'check an image’s signature and SBOM attestation with cosign',
    href: onMain('scanner/README.md#verify-a-published-image'),
  },
  {
    title: 'API reference',
    hint: 'every route, who may call it, and what it returns',
    href: onMain('docs/API.md'),
  },
]

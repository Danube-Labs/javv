# javv - brand guide

**javv** (*just another vulnerability viewer*) · by **Danube Labs**

The mark: a magnifying glass - the viewer - holding a dusk river scene: a low sun
above the horizon and the Danube meandering toward the viewer. Warm dusk palette
on dark slate, flat hand-editable vector.

---

## Files

| File | Use |
|---|---|
| `icon.svg` | Primary mark, 64-unit grid, squircle tile. App icons, avatars, anywhere ≥ 24 px |
| `icon-dark.svg` | Same + hairline edge, for pure-black / very dark backgrounds |
| `favicon.svg` | Simplified (no river/ridge, chunkier strokes) for 16–32 px |
| `wordmark.svg` / `wordmark-dark.svg` | `javv` + small "by Danube Labs" credit |
| `lockup.svg` / `lockup-dark.svg` | Icon + wordmark + credit, horizontal |
| `github/avatar.svg` | Org/profile avatar source (works in circle crop) |
| `github/readme-hero.svg` | README banner source, 1280×360 |
| `github/social-card.svg` | Social preview source, 1280×640 |
| `github/png/*` | Raster exports - **use these on GitHub** (see below) |

## Color

| Name | Hex | Role |
|---|---|---|
| Danube Slate | `#16232F` | Tile, dark backgrounds, wordmark on light |
| River Slate | `#21384A` | Water inside the lens |
| Dusk Coral | `#EC7E54` | Sky gradient bottom, accents |
| Amber | `#F4A368` | Lens rim + handle, river gradient bottom |
| Dusk Peach | `#F7B57E` | Sky gradient top |
| Ridge | `#C76A55` | Horizon ridge (55% opacity) |
| Sunlight | `#FCE7C1` | Sun, river gradient top |
| Paper | `#F3EEE6` | Light backgrounds, wordmark on dark |

**Severity firewall:** brand chrome stays in coral/amber - never pure red, and
never the in-app severity ramp (Critical/High/Medium/Low). A logo and a CVE
badge must never be confusable.

## Type

The brand uses the app's two faces, so the logo and the product read the same:

- **Hanken Grotesk 700** - wordmark (`javv`), headings. Letter-spacing -0.03em, the same as the
  app's sidebar wordmark.
- **Spline Sans Mono 400/700** - credit line, taglines, code. Credit format:
  `by ` (regular, muted) + `Danube Labs` (bold, slightly stronger).
- Both are free fonts under the SIL Open Font License. The app serves its own copies
  (`frontend/src/styles/fonts.css`); the text-bearing SVGs here name the families in a `<style>`
  and need them installed to render as designed.
- Until 2026-10 the brand used Space Grotesk and Space Mono. The app moved to Hanken Grotesk
  (2026-07-09) and Spline Sans Mono (2026-10-12) by operator rulings on built specimens, and the
  brand followed (issue 818).

## Usage rules

- Clear space: ¼ of the mark's width on all sides.
- Minimum sizes: full icon 24 px; below that use `favicon.svg` (down to 16 px).
- Emphasis: **javv** is the product and always leads; "by Danube Labs" stays
  small and muted - never larger than ~⅛ of the wordmark height.
- Don't redraw the scene, recolor the rim, or put the warm palette on red.
- The icon already includes its tile - don't add another container around it.

## GitHub notes

GitHub strips webfonts from SVGs rendered as images, so **text-bearing art ships
as PNG** (fonts baked in at exact size):

- Repo/product avatar → `github/png/avatar-512.png` (the JAVV mark; shows correctly in circle crop)
- README hero → `github/png/readme-hero-1280x360.png`
- Repo social preview → `github/png/social-card-1280x640.png` (GitHub requires raster here anyway)
- Docs favicon → `favicon.svg` (SVG is fine for browsers) + `github/png/favicon-32.png` fallback

Shape-only SVGs (`icon`, `favicon`, `avatar`) contain no text and are safe to
embed anywhere, including READMEs.

**The Danube-Labs org avatar is the company mark, not the JAVV mark**, and is deliberately
not one of the assets above: an org wearing one product's icon stops making sense the moment
there is a second product. It has no source file in this folder; it lives only as the
uploaded org image on GitHub. Add it here if it ever needs to be reproduced.

To hand-edit text-bearing SVGs in a vector tool without the webfont installed,
install Hanken Grotesk / Spline Sans Mono locally first (or outline the text to paths
before sending to anyone who won't have them).

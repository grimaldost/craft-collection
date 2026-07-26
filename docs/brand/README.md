# convoy — brand kit &middot; house system v1

House identity for the family: **keel &middot; convoy &middot; fathom &middot; mantis &middot; craft-collection**.
Shared construction, one accent hue per project. This file plus `assets/` is the full
spec; a sibling kit is derived mechanically (&sect;8) without new design decisions.

## 1 &middot; System summary

- **Mark** — a 24-unit grid carrying a 20&times;20 accent **tile** (corner radius 3) with the
  project's **figure cut out as true transparency** (`fill-rule="evenodd"`). One SVG file
  works on any background, GitHub light or dark.
- **Figure** — drawn from *bands*: straight-edged strips ~3.8u thick, 45&deg; or axis-aligned.
  convoy's figure is a double chevron (escorted column, moving right).
- **Wordmark** — constructed monoline lowercase (&sect;3). No font dependency in committed SVGs.
- **Asset text** — none beyond the wordmark for now; if reintroduced, see &sect;4.
- **Accent** — one hue per project (&sect;5); neutrals are shared house-wide.
- No mascots, no gradients, no faux-3D, no attribution footers.

## 2 &middot; Mark construction

```
viewBox            0 0 24 24
tile               x2 y2 w20 h20, corner r3, filled with accent
figure             cut out of the tile (evenodd subpaths), never drawn on top
band thickness     3.8u measured on the vertical (2.7u perpendicular at 45deg)
figure margins     >= 3.8u to tile edges; >= 2.0u between bands (the "waist")
convoy bands       back edges x6.4 / x12.2; apexes x12.4 / x18.2; span y6..y18
```

Tile fill: `#A45E05` on light, `#C17930` on dark (see &sect;9 for the `<picture>` pattern).
Never outline the tile, never recolor it per-context, never rotate the figure.
Minimum size 16&nbsp;px; the mark alone is the favicon / avatar.

```svg
<path fill="#A45E05" fill-rule="evenodd" d="M5 2 H19 A3 3 0 0 1 22 5 V19 A3 3 0 0 1 19 22 H5 A3 3 0 0 1 2 19 V5 A3 3 0 0 1 5 2 Z M6.4 6 L12.4 12 L6.4 18 L6.4 14.2 L8.6 12 L6.4 9.8 Z M12.2 6 L18.2 12 L12.2 18 L12.2 14.2 L14.4 12 L12.2 9.8 Z"/>
```

## 3 &middot; Wordmark construction

Lowercase, monoline, geometric — drawn, not typeset, so committed SVGs never depend
on a font being installed.

```
x-height   14u          stroke        3.6u, butt terminals
rounds     r5.3 centerline (o, c, n arch)   c opening: 80deg, facing right
diagonals  v, y filled polygons, flat baseline cut; y descender to 19.5u
gaps       3.3-4.2u between letter boxes (as kerned in the file)
```

Lockup: tile height 20u, gap tile&rarr;wordmark 10u, wordmark x-height centered on tile
center. The SVG files are the source of truth — do not retype the name in a font.

## 4 &middot; Typography (READMEs and docs)

- Headings and body: GitHub's default system sans. Sentence case, descriptive, no
  marketing register.
- Any text inside SVG assets (labels, metadata), if ever reintroduced: the system
  monospace stack — `ui-monospace, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace`,
  always English. Current state: assets carry no text beyond the wordmark (&sect;7).

## 5 &middot; Color tokens

House neutrals:

| token | hex | use |
|---|---|---|
| ink-950 | `#0E1114` | dark background |
| ink-900 | `#171B1F` | wordmark / ink on light |
| ink-700 | `#2A3238` | badge label bg; secondary text on light |
| ink-500 | `#5C666E` | muted text (AA on both paper and ink-950) |
| ink-300 | `#9AA4AC` | muted text on dark |
| ink-150 | `#D8DDE0` | hairlines on light |
| paper   | `#FBFBFA` | light background; text on dark |

Project accents (equal lightness/chroma per step, oklch-derived):

| project | 300 | 500 | 700 | hue |
|---|---|---|---|---|
| convoy | `#D89C67` | `#C17930` | `#7F4400` | signal amber |
| keel | `#7FAEE9` | `#558ED6` | `#255691` | hull steel |
| fathom | `#4FBEC4` | `#00A2AA` | `#00666D` | sounding teal |
| mantis | `#C398D6` | `#A973C0` | `#6C407F` | iridescent violet |
| craft | `#8FB979` | `#6A9D4B` | `#39621C` | workshop green |

Roles: **500** tile on dark; **600-level** tile on light (convoy: `#A45E05`); **700** accent
text on paper and background for white text; **300** accent graphics/text on ink-950.

Contrast (AA): white on any *-700 &ge; 6.5:1 &check;. *-700 text on paper &ge; 6.5:1 &check;.
*-300 on ink-950 &ge; 7.9:1 &check;. Tiles are non-text graphics (&ge; 3:1 on both themes &check;).
Never set body text on 300/500 accent fills.

## 6 &middot; Badge spec (shields.io)

Style `flat-square`. Label background always `labelColor=2A3238`, white text.
Message color: version/meta badges use the project's *-700; cross-family references use
the *sibling's* *-700; CI/status badges keep shields' semantic defaults.
Recommended order, max five: **ci &middot; version &middot; method &middot; docs**.

```
https://img.shields.io/github/actions/workflow/status/OWNER/convoy/ci.yml?style=flat-square&labelColor=2A3238
https://img.shields.io/github/v/tag/OWNER/convoy?style=flat-square&labelColor=2A3238&color=7F4400&label=version
https://img.shields.io/badge/method-keel-255691?style=flat-square&labelColor=2A3238
https://img.shields.io/badge/docs-md-2A3238?style=flat-square&labelColor=2A3238
```

## 7 &middot; Banner composition (house layout, every project)

Hero `1280x240`: 1px frame (r8), lockup centered at 3.8&times;. No text beyond the wordmark.
Light and dark files; embed with `<picture>` (&sect;9).

Social card `1280x640`: always the dark composition — ink-950 field, centered lockup at
5.2&times;, project figure as a 7% watermark bleeding off the right edge. No text beyond the
wordmark.
GitHub's social-preview upload needs raster: export the provided PNG (or re-render the
SVG at 1:1) and upload under repo Settings &rarr; Social preview.

## 8 &middot; Deriving a sibling kit

1. Copy `assets/`, swap the accent tokens (&sect;5 row) in every file.
2. Swap the figure subpaths in mark/lockup/hero/social for the project's figure (below);
   the tile, grid, margins and band rules do not change.
3. Rebuild the wordmark from the letter library (c o n v y exist; draw new letters with
   &sect;3 rules as needed).
4. Reuse the hero and social compositions verbatim (&sect;7).

| project | figure (all bands 3.8u unless noted) |
|---|---|
| convoy | double chevron, back edges x6.4/x12.2, apexes x12.4/x18.2, span y6..18 |
| keel | spine + sole: vertical band x10.5..13.5 y5..15.5; base band x6.5..17.5 y15.5..18.5 |
| fathom | three soundings, widths 5.5 / 9 / 12.5u centered, y5.5..8 / 10.75..13.25 / 16..18.5 |
| mantis | diamond band: outer (12,4.2)(19.8,12)(12,19.8)(4.2,12), inner inset 3.54 on axes |
| craft | frame band: outer square 6.5..17.5, inner 9.5..14.5 (the jig) |

## 9 &middot; Files &amp; usage

```
assets/convoy-mark-light.svg      assets/convoy-mark-dark.svg
assets/convoy-wordmark-light.svg  assets/convoy-wordmark-dark.svg
assets/convoy-lockup-light.svg    assets/convoy-lockup-dark.svg
assets/convoy-hero-light.svg      assets/convoy-hero-dark.svg
assets/convoy-social-card.svg     assets/convoy-social-card.png
```

Theme-correct embed (README hero; same pattern for mark/lockup):

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/convoy-hero-dark.svg">
  <img alt="convoy" src="assets/convoy-hero-light.svg" width="100%">
</picture>
```

# Brand assets

craft's visual identity, part of a shared house system across the project family.
The SVGs are self-contained - every glyph and shape is an outlined path, so nothing
depends on an installed font or a network fetch - and they are the source of truth:
edit them as code rather than re-exporting from a design tool.

> The asset files are named `craft-*` and the wordmark reads **craft** - the family
> short name for this repo (`craft-collection`).

| File | What | Where it is used |
|---|---|---|
| `craft-mark-{light,dark}.svg` | The mark alone: accent tile with the jig figure (an inverted U) cut out as true transparency | Favicon / avatar; anything down to 16 px |
| `craft-wordmark-{light,dark}.svg` | The wordmark alone | Inline naming |
| `craft-lockup-{light,dark}.svg` | Mark + wordmark | Headers |
| `craft-hero-{light,dark}.svg` | 1280x240 banner: framed, centered lockup | Top of [README.md](../README.md) |
| `craft-social-card.svg` / `.png` | 1280x640 dark card: lockup over a figure watermark | GitHub Settings -> Social preview (upload the PNG) |

## Embedding

GitHub renders READMEs in both light and dark; embed the theme pair with `<picture>`:

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/craft-hero-dark.svg">
  <img alt="craft" src="assets/craft-hero-light.svg" width="100%">
</picture>
```

The same pattern applies to the mark and the lockup.

## Tokens and rules

- Accent (workshop green): tile `#508130` on light, `#6A9D4B` on dark. The wordmark
  is ink on light and paper on dark; this kit uses no accent in the wordmark itself. House neutrals: ink `#171B1F`, paper
  `#FBFBFA`, muted `#5C666E`, badge-label `#2A3238`.
- This wordmark carries no accent rule; keel, fathom, mantis and sealore have one.
- Badges: shields.io `flat-square`, always `labelColor=2A3238`; version and meta
  badges use `39621C`; CI and status badges keep shields' semantic defaults; at most
  five in the row.
- The tile is never outlined, recolored per context, or rotated; minimum mark size
  16 px.
- The assets carry no text beyond the wordmark.

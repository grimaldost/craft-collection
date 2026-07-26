<!-- Family README template - house layout v1.
     Rhythm rules:
     - hero first, nothing above it; height <= 240px
     - badges immediately under the hero, one row, max 5
     - pitch: ONE paragraph, 3-4 sentences, no headings before it
     - quick start within the first screenful; one copy-pastable block
     - how-it-works: one short block per pillar, no walls of text
     - end with docs links + family footer; no marketing sections -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/convoy-hero-dark.svg">
  <img alt="convoy" src="assets/convoy-hero-light.svg" width="100%">
</picture>

![ci](https://img.shields.io/github/actions/workflow/status/OWNER/convoy/ci.yml?style=flat-square&labelColor=2A3238)
![version](https://img.shields.io/github/v/tag/OWNER/convoy?style=flat-square&labelColor=2A3238&color=7F4400&label=version)
![method](https://img.shields.io/badge/method-keel-255691?style=flat-square&labelColor=2A3238)

**convoy** decomposes a body of work into PR-sized tasks, drives a coding agent through
each one under pinned budgets, gates every result with deterministic checks, and
integrates the branches that pass. <!-- pitch: what it does, in the project's own verbs -->

## Quick start

```sh
# install, configure, first run - keep to one block
```

## How it works

**Governed** — every task runs under pinned budgets and an explicit spec.

**Gated** — results merge only through deterministic checks; red never lands.

**Measurable** — each run emits a scored, auditable record.

## Documentation

- [Concepts](docs/concepts.md)
- [Configuration](docs/configuration.md)
- [CLI reference](docs/cli.md)

---

<sub>Part of the <a href="#">keel</a> &middot; convoy &middot; <a href="#">fathom</a> &middot; <a href="#">mantis</a> &middot; <a href="#">craft</a> family.</sub>

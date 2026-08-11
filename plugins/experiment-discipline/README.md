# experiment-discipline

Discipline for **evaluation acts** — any piece of work whose correct answer is a
valuative claim ("is this effective", "which is better", "is it worth it"). The
question it forces is not "did it run" but "could a reader reconstruct the method
and see the uncertainty".

## Skills

- **experiment-rigor** (rigid) — turn an experiment into a typed `record.yaml`
  whose `report.md` is derived, across a probe / measurement / decision tier
  ladder. Every load-bearing rule is a script that exits non-zero with a stable
  error code, not a line of prose to remember. The dividing line: methods
  uncertainty is disqualifying, effect uncertainty is declarable.

## Mechanism

`skills/experiment-rigor/scripts/` is the skill, not an accessory to it:

- `validate.py` — the central gate. Stable codes (`ER-SCHEMA`, `ER-RECON`,
  `ER-STATS`, `ER-PREREG`, `ER-ANCHOR`, `ER-XCHECK`, `ER-THREAT`, `ER-PROBE`,
  `ER-PARITY`, `ER-LINK`, `ER-COMPREHEND`), exit 1 on any failure.
- `render.py` — derives `report.md` from the record and gates the pair against
  drift (`--check`); also generates `templates/SCHEMA.md` from `schema.json`.
- `stats.py` — small-n intervals with no CLT path below n=30 (Wilson,
  Clopper-Pearson, within-experiment Beta-Binomial, paired/clustered SEs).
- `from_fathom.py` — build a record's run block from a fathom ledger.

`templates/` carries one skeleton per tier plus the machine-readable
`schema.json` and its generated field guide; `references/` carries the small-n
statistics notes and the threats catalog; `examples/rg-2x2/` is the founding
dogfood record — the chain root every later record's prior links back to.

## Gates that travel with a record

Two pre-commit hooks select every travelling `record.yaml` / `report.md` pair and
run `validate.py` and `render.py --check` over it, so a record cannot be
committed out of sync with its report or with its own frozen pre-registration.

**Which install surface carries them.** `/plugin install` carries the skill, the
scripts, the templates and the references — it does not carry commit-time gates,
because a Claude Code plugin has no way to install one. The gates come from the
repository's `.pre-commit-hooks.yaml`, which every consumer project can reference
by URL:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/grimaldost/craft-collection
    rev: <tag or sha>
    hooks:
      - id: experiment-rigor-validate
      - id: experiment-rigor-render-check
```

The default pattern matches any `record.yaml`; narrow it with `files:` once your
records have a home, and see the note in `.pre-commit-hooks.yaml` before widening
the drift gate to `report.md`. PyYAML is the gates' only non-stdlib dependency
and `uv run --with pyyaml` supplies it, so nothing is installed into the
consumer's environment.

**On Windows, prefer the local form.** The by-URL export runs through
pre-commit's `language: script`, which resolves the entry's `#!/usr/bin/env
python3` shebang — and on a stock Windows install that resolves to the Microsoft
Store app-execution alias, which exits 9009 without running anything (measured
2026-08-11; it hits every hook this repository exports, not only these two). The
hooks fail closed, so nothing passes hollow, but they are unusable there. Pin the
interpreter yourself instead, with the plugin's installed path:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: experiment-rigor-validate
        name: experiment-rigor record validator
        entry: uv run --no-project --with pyyaml -- python
          /path/to/experiment-discipline/skills/experiment-rigor/scripts/validate.py
        language: system
        files: (^|/)record\.yaml$
        pass_filenames: true
```

This is the form this repository uses on itself, and it is the one to copy for
any project whose commits happen on Windows.

## Freeze durability

A measurement-tier record pins its frozen pre-registration by commit
(`plan_frozen_at.commit`) **and** by the path it had at that commit
(`plan_frozen_at.path`) — `git show` does not follow renames, so the coordinate
survives a relocation. Each freeze commit also carries a lightweight keep-ref tag
so a squash-merge cannot orphan it; see
`skills/experiment-rigor/examples/rg-2x2/FREEZE.md` for the choreography.

## Install

```text
/plugin install experiment-discipline@craft-collection
```

Local development: `claude --plugin-dir ./plugins/experiment-discipline`.

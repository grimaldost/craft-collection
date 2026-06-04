---
name: refresh-stack
description: Review and update the python-engineering toolchain pins. Run /refresh-stack to detect which pinned tools are behind the latest PyPI release, read the relevant changelogs, and produce a reviewable changeset (stack.toml version bumps plus any guidance edits) for approval. Mechanical bumps are applied on approval; guidance edits are never auto-applied. Manual-only.
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash, Read, Edit, Grep, WebFetch
---

# Refresh Stack

The LLM-assisted update leg of the freshness loop. Detection is mechanical
(`check_versions.py`); **this command does the reasoning** — reading changelogs
and deciding what, if anything, the guidance should say differently. Never
auto-apply guidance edits; propose, then let the user approve.

The `stack.toml` and scripts live in the sibling `python-engineering` skill of
this plugin — resolve it as `${CLAUDE_PLUGIN_ROOT}/skills/python-engineering/`
(fall back to the path relative to this file if the variable isn't set).

## Workflow

1. **Detect.** Run the version check and capture JSON:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/python-engineering/scripts/check_versions.py" --json
   ```
   The `behind` flag marks any tool whose pinned floor is behind a newer
   major/minor. If `behind_count` is 0, report "stack current" and stop.

2. **Read the changes.** For each behind tool, fetch its changelog / release
   notes for the range between `pinned_min` and `latest` (WebFetch the project's
   releases page or changelog; use context7 for library docs). Do not guess from
   the version number alone.

3. **Classify each delta** into one of three buckets:
   - **version-only** — no behavior or guidance impact; just a newer release.
     Action: bump `pinned_min` in `stack.toml`.
   - **guidance-affecting** — the release changes a recommendation, renames a
     rule/flag, deprecates an API, or adds a pattern the skill should mention
     (e.g. a ruff rule rename, a `ty` milestone, a new PEP default). Action:
     propose a specific prose edit to `SKILL.md` or a reference, quoting the
     changelog entry that motivates it.
   - **needs-human** — an ecosystem shift or judgment call (e.g. whether `ty`
     should replace `mypy` as the default). Action: flag it; do not decide.

4. **Present a reviewable changeset**, grouped:
   - a `stack.toml` diff of the mechanical `pinned_min` bumps. (Pre-commit hook
     revs in `[precommit]` are passed through *un-checked* — `check_versions.py`
     emits no "behind" signal for them — so bump a hook rev only after manually
     checking its repo's latest tag, or leave it.)
   - the proposed guidance edits, each with its cited rationale,
   - the needs-human list.

5. **On approval:** apply **only** the mechanical `stack.toml` bumps (and any
   guidance edits the user explicitly approved — never silently). Stamp the review
   date from the check's `checked_at` field (not the model's sense of "today"), in
   **both** places it appears: `[meta] last_reviewed` in `stack.toml`, and the
   human-visible "last reviewed" line in the `python-engineering` and
   `data-engineering-discipline` SKILL.md files — the machine stamp and the
   reader-facing stamp must not drift apart. Leave the plugin `version` bump and
   commit to the user.

## Guardrails

- This embodies the data-engineering discipline applied to the skill itself:
  *source of truth is observable* (verify against PyPI + changelogs, never infer)
  and *all change is intentional and traceable* (a reviewed diff with cited
  rationale, never a silent edit).
- Mechanical version bumps are safe to apply on approval. Guidance edits change
  what the skill *recommends* — those always wait for explicit sign-off.
- If the changelog is ambiguous about whether a change affects guidance, treat
  it as needs-human rather than guessing.

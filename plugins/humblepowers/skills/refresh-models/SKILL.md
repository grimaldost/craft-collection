---
name: refresh-models
description: Review and update the choosing-models tier data. Run /refresh-models to detect lineup drift against the platform's current model list, read the release notes, and produce a reviewable changeset (models.toml lineup edits plus any guidance edits) for approval. Mechanical lineup changes are applied on approval; threshold and doctrine edits are never auto-applied without calibration evidence. Manual-only.
disable-model-invocation: true
user-invocable: true
allowed-tools: Bash, Read, Edit, Grep, Glob, WebFetch
---

# Refresh Models

The update leg of the choosing-models freshness loop. Detection compares data
sources already in the session; **this command does the reasoning** — reading
release notes and deciding what, if anything, the tier table should say
differently. Never auto-apply threshold or doctrine edits; propose, then let
the user approve.

The data file lives in the sibling `choosing-models` skill of this plugin —
resolve it as `${CLAUDE_PLUGIN_ROOT}/skills/choosing-models/models.toml` (fall
back to the path relative to this file if the variable isn't set). Project
overrides of that file are refreshed the same way, in their own location.

## Workflow

1. **Detect.** Run the check rather than performing it by hand:

   ```bash
   uv run --no-project -- python \
     "${CLAUDE_PLUGIN_ROOT}/skills/choosing-models/scripts/lineup_check.py" <session model id>
   ```

   It exits 1 and names the absent model when the session is running on
   something the tier data does not list — the environment tripwire, as a
   command. Then compare `models.toml` against the platform's model reference
   (e.g. the claude-api skill's current-models table, the session environment's
   lineup note where present, or the published models documentation via
   WebFetch) for the drift a single id cannot show: a current model missing from
   the table, a listed model no longer current, or `review_by` in the past. No
   drift and not past `review_by` → report "lineup current" and stop.

2. **Read the changes.** For each drifted entry, read the vendor's release
   notes or model documentation for what actually changed — capability tier,
   pricing shape, tokenizer, knobs. Do not guess from the model name alone.

3. **Classify each delta:**
   - **lineup-only** — a new model slots into an existing tier, an alias or
     availability changed. Action: edit the `[[models]]` rows.
   - **guidance-affecting** — a tier assignment or threshold should move, or a
     cost caveat changed. Action: propose the edit *plus* the calibration it
     needs — threshold moves ride observed-run evidence from a registered
     eval harness when one is installed (e.g. fathom's recalibration
     playbook), never a release note alone.
   - **needs-human** — a judgment call (a new tier, a pricing regime change).
     Flag it; do not decide.

4. **Present a reviewable changeset**, grouped: the mechanical `models.toml`
   diff, the proposed guidance edits with cited rationale, the needs-human
   list.

5. **On approval:** apply the mechanical edits (and only explicitly approved
   guidance edits). Stamp `last_reviewed` and advance `review_by` (quarterly
   by default) in `models.toml`.

6. **Walk the mirror sites.** Downstream copies of tier/model/price data are
   registered in a bindings file — `$MODEL_MIRRORS_FILE`, else
   `~/.claude/model-mirrors.toml` — because a plugin cannot know a given
   stack's mirrors. Absent, ask once and proceed without the walk; never hunt
   the filesystem. Walk each registered site, honour its `vocabulary` (a
   family-named copy is translated, not substituted), and propose the edit in
   that repo's own change process. Close with the grep either way: search for
   the *outgoing* model string and report any hit as a candidate mirror.
   Format, fields, and the rule it enforces: `references/mirrors-file.md`.

## Guardrails

- *Source of truth is observable*: verify against the platform reference and
  release notes, never infer; *all change is intentional and traceable*: a
  reviewed diff with cited rationale, never a silent edit.
- Threshold and tier-assignment changes without calibration evidence are
  needs-human by definition.
- Leave the plugin `version` bump and commit to the user.

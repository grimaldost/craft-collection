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

1. **Detect.** Compare `models.toml` against the platform's model reference
   (e.g. the claude-api skill's current-models table, the session environment's
   lineup note where present, or the published models documentation via
   WebFetch). Drift means a current model missing from the table, a listed
   model no longer current, or `review_by` in the past. No drift and not past
   `review_by` → report "lineup current" and stop.

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
   supplied by a user binding (a mirror-sites table in project or user
   memory — e.g. an engine's tier map, an eval harness's price fallback, a
   template's pinned model strings), since a plugin cannot know a given
   stack's mirrors. Walk each registered site and propose its matching edit
   in that repo's own change process. With no binding registered, skip —
   then close with the grep: search the working repos for the *outgoing*
   model string and report any hit as a candidate mirror to register.

## Guardrails

- *Source of truth is observable*: verify against the platform reference and
  release notes, never infer; *all change is intentional and traceable*: a
  reviewed diff with cited rationale, never a silent edit.
- Threshold and tier-assignment changes without calibration evidence are
  needs-human by definition.
- Leave the plugin `version` bump and commit to the user.

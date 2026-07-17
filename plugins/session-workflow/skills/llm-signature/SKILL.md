---
name: llm-signature
description: >
  Sign agent-assisted work with a machine-generated provenance signature: an
  Assisted-By git trailer naming the exact model that wrote and orchestrated the
  change, and an Agent-Stack trailer naming the harness and plugin versions it
  ran on. Use when committing or writing a PR body in a project that adopts the
  signature, when asked to sign a commit with the model / add model attribution
  or an LLM signature, when asked which model or tool stack produced a change,
  or when replacing Co-Authored-By AI boilerplate with provenance trailers. The
  signature is rendered by a script from live sources, never typed from memory,
  and the model is listed only in Assisted-By — never as a commit co-author. Not
  for human authorship credit (real co-authors keep their Co-Authored-By lines).
---

# LLM Signature

Provenance, not marketing. A `Co-Authored-By: Claude <noreply@anthropic.com>`
line says an AI touched the commit and nothing else; this signature records
what actually shaped the work — the exact model and the versioned tool stack —
as machine-readable git trailers:

```text
Assisted-By: claude-sonnet-5
Agent-Stack: claude-code@2.1.0; engineering-discipline@2.1.0 (craft-collection); session-workflow@0.15.0 (craft-collection)
```

Trailers are the native mechanism: hidden from `git log --oneline`, filterable
with `git log --format='%(trailers:key=Assisted-By)'`, parseable with
`git interpret-trailers`. Full grammar and semantics: `references/spec.md`.

## Semantics

- `Assisted-By` names the model that is **writing and orchestrating** — the one
  responsible for the change. One model: the orchestrator at commit time, not
  every subagent it delegated to. The model is never added as a commit
  co-author or committer; this trailer is its only appearance.
- `Agent-Stack` is **environment-at-commit** provenance: the harness and the
  enabled plugins, each as `name@version (marketplace)` — what was installed
  and enabled, not a claim that every item fired. The marketplace label is a
  lookup key (its repo or `claude plugin marketplace list` resolves it) — URLs
  stay out of commits.

## Generate — always by script, never by hand

A remembered version is wrong the moment anything updates, so the signature is
rendered from live sources every time:

```bash
uv run --no-project -- python "${CLAUDE_PLUGIN_ROOT}/skills/llm-signature/scripts/render_signature.py"
```

The model comes from the session transcript (last main-loop assistant message —
subagent sidechains never sign; a discovered transcript signs only when fresh
and verified against this cwd); the stack comes from `claude plugin list` and
`claude --version`. `--json` for machine use, `--plugin <name>` (repeatable) to
narrow the stack, `--model` / `--transcript` as explicit overrides. If the
model cannot be resolved, the script fails rather than guessing — do not
substitute a hand-typed signature; commit unsigned or fix the resolution.

## Apply

**Commits** — in a project that adopts the signature (one declaration in the
repo's CLAUDE.md; see `references/spec.md` § Adopting), run the script at
commit time and append its output verbatim as the final paragraph of the
commit message. Drop any `Co-Authored-By` line carrying the vendor's identity
(an anthropic.com or claude+noreply address) and any "Generated with Claude
Code" badge — the signature replaces both. Real human co-authors keep their
lines, even one named Claude.

**PR bodies** — same block, fenced as `text`, at the end of the description.

**Mechanical enforcement (optional)** — `--apply <msg-file>` rewrites a commit
message in place (scrub boilerplate, refresh trailers, never fail the commit),
built to be wired as a git `prepare-commit-msg` hook; recipe in
`references/spec.md`.

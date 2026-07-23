---
name: toolkit-awareness
description: Know what skills, agents, commands, and hooks are installed in the current Claude Code environment, and reference them well in prompts and specs. Use when answering "what tools/agents/commands/hooks do I have" (including narrower inventory questions like which hooks are configured), determining which installed skill owns or is responsible for a given concern — a scoring rubric, a schema, project conventions — so you point at the owner instead of duplicating it, planning work that will run in Claude Code, or writing a task spec or definition-of-done that should reference slash commands or quality gates. Produces a live inventory via a scan script rather than relying on a hand-maintained list.
---

# Toolkit Awareness

Two jobs: get a **live** picture of what's installed, and reference it well in
prompts and specs. The inventory is generated on demand — nothing
hand-maintained to drift.

## Get the live inventory

Run the scan script; it enumerates skills, commands, agents, and hooks from
user-level (`~/.claude`) and project-level (`<repo>/.claude`) configuration:

```bash
# A skill runs with cwd = the user's project, not the skill dir — use the absolute path.
uv run --no-project -- python "${CLAUDE_PLUGIN_ROOT}/skills/toolkit-awareness/scripts/scan_toolkit.py"          # grouped table
uv run --no-project -- python "${CLAUDE_PLUGIN_ROOT}/skills/toolkit-awareness/scripts/scan_toolkit.py" --json   # machine-readable
```

The scan also lists **plugin-provided** components via `claude plugin list`
(they live in the plugin cache, not `.claude/`). Without the CLI (another
harness), it still reports the `.claude/` tree and flags plugins as not
enumerated — fall back to a repo's generated `AGENTS.md` index when one
exists, else a directory scan of its `plugins/*/skills/`.

Prefer the scan over memory: a remembered list is wrong the moment something
changes.

The same script is wired as a SessionStart hook (`--session-start`), inert
unless `TOOLKIT_AWARENESS_INJECT=1`. That path caches its output (fingerprint
over settings and plugin manifests, 24h TTL) so a warm start skips the slow
CLI call; `--no-cache` forces a scan; table and `--json` modes never touch the
cache. It also diffs hook commands recorded in the session transcript against
every installed `hooks.json` and warns on a mismatch — the signature of an
app-level **frozen plugin snapshot**, where every disk layer reads "current"
but the running session is weeks behind; verify headless (`claude -p`). On
demand: `--check-serving <transcript_path>` (always exits 0).

## How to reference the toolkit in prompts and specs

When writing a task prompt or a definition-of-done that another agent session
will execute, lean on what's installed instead of restating it:

1. **Don't restate conventions a skill already handles.** Write "follow the
   invariants in `<conventions skill / GUARDRAILS path>`" rather than copying the
   rules. Convention skills fill in the detail automatically.
2. **Reference slash commands in the Definition of Done**, e.g.:
   ```markdown
   - [ ] `/<review-command>` returns an APPROVE verdict
   - [ ] `/<gate-command>` reports no blocking failures
   ```
3. **Don't tell a prompt to "use agent X".** Claude Code delegates to subagents
   automatically; agents are invisible to task prompts and naming one is noise.
4. **Reference schemas, configs, and templates by name** when a reference skill
   resolves them — name the artifact, let the skill supply the content.
5. **Name the quality gates, not their internals.** "Pass the pre-commit and
   type-check gates" is portable; pasting the gate config into the prompt is not.

## When multiple skills could apply

Know which skill *owns* what and reference the owner instead of inlining a
stale copy — one skill owns a scoring rubric, another project conventions,
another a schema. The scan's descriptions are the fastest way to see who owns
what.

## Source of truth

Skills are condensed copies of authoritative docs; on conflict the doc
(CLAUDE.md, a guardrails file, a schema doc) wins — update the skill. The
inventory says *what exists*; the docs stay the truth for *what's correct*.

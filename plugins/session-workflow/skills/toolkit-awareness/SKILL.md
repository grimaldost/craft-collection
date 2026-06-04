---
name: toolkit-awareness
description: Know what skills, agents, commands, and hooks are installed in the current Claude Code environment, and reference them well in prompts and specs. Use when answering "what tools/agents/commands/hooks do I have", planning work that will run in Claude Code, or writing a task spec or definition-of-done that should reference slash commands or quality gates. Produces a live inventory via a scan script rather than relying on a hand-maintained list.
---

# Toolkit Awareness

Two jobs: get a **live** picture of what's installed, and reference it well when
authoring prompts and specs. The inventory is generated on demand — there is no
hand-maintained list to drift out of date.

## Get the live inventory

Run the scan script; it enumerates skills, commands, agents, and hooks from
user-level (`~/.claude`) and project-level (`<repo>/.claude`) configuration:

```bash
# A skill runs with cwd = the user's project, not the skill dir — use the absolute path.
python "${CLAUDE_PLUGIN_ROOT}/skills/toolkit-awareness/scripts/scan_toolkit.py"          # grouped table
python "${CLAUDE_PLUGIN_ROOT}/skills/toolkit-awareness/scripts/scan_toolkit.py" --json   # machine-readable
```

The scan also lists **plugin-provided** components (it shells out to
`claude plugin list`), since those live in the plugin cache rather than `.claude/`
— the case a directory-only scan misses. For deeper detail on one plugin, use
`claude plugin details <name>`.

Prefer the scan over recalling from memory: installed capabilities change, and a
remembered list is wrong the moment one does.

## How to reference the toolkit in prompts and specs

When writing a task prompt or a definition-of-done that another Claude Code
session will execute, lean on what's installed instead of restating it:

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

Know which skill *owns* what, so you reference the owner and don't duplicate it.
Typical ownership boundaries in a mature setup: one skill owns a scoring rubric
or template, another owns project conventions, another owns a schema reference.
When a prompt needs something, point at the owning skill rather than inlining a
stale copy. The scan's descriptions are the fastest way to see who owns what.

## Source of truth

Skills are condensed copies of authoritative docs. If a skill and the underlying
doc (CLAUDE.md, a guardrails file, a schema doc) conflict, the doc wins — update
the skill. The live inventory tells you *what* exists; the docs remain the
source of truth for *what's correct*.

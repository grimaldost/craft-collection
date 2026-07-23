# Cold start — arming the protocol without the plugin surface

The sessions that most need this protocol are the likeliest to lack its plugin
surface: a running session whose plugin snapshot predates the skill, an SDK or
harness session whose skill menu omits it, a machine where the hook was never
enabled mid-flight. Every piece degrades to a by-hand equivalent; this is the
recipe (field-validated on a 36-hour campaign that was enabled exactly this
way and lost no state across compactions, restarts, and a session takeover).

## Minimal contract — keep this reachable without the skill

This recipe lives inside the skill, so it is unreachable in exactly the sessions
that need it (menu omits the skill). Mirror the compact contract below into the
project or global CLAUDE.md protocol snippet, where a menu-less session still has
it — enough to arm a hook-compatible anchor with nothing installed:

- Anchor at `<project>/.claude/anchors/<date>-<slug>.md`, one file, overwritten.
- `<!-- anchor:tail -->` on its own line: the hook injects only the HEAD above it.
- HEAD carries a **Cursor** with a single next action; keep it near the top.
- Close by renaming to `<name>.closed.md` — the rename is the only close signal.

The fuller by-hand recipe (hook registration, verify step) follows.

## The anchor file, by hand

The anchor format is a convention, not a command's private output — reproduce
it from the skill body's section list (mission, plan pointer, cursor,
invariants, last-known-good, resume steps). What matters beyond the sections:

- Path: `<project>/.claude/anchors/<date>-<slug>.md`. One file, overwritten
  atomically.
- Put `<!-- anchor:tail -->` on its own line between the resume steps and the
  decisions log: the hook injects only what is above it, so the append-only
  tail never crowds the live state out of the injection budget.
- When the run ends, rewrite the anchor to a minimal landed stub (status, a
  one-line outcome, resume: none), then rename to `<name>.closed.md` — the
  rename is the only close signal the hook honors; a prose "status: CLOSED"
  line does not stop re-injection.
- Add a `source: maintained by hand` line so a later reader knows no command
  wrote it.

The `/anchor` command is a convenience wrapper around exactly this file;
writing it by hand is the same operation.

## The re-injection hook, registered manually

A running session pins the plugin snapshot it started with, so a hook that
shipped after the session began is invisible to it. Register the same hook
directly in the project's `.claude/settings.local.json` (the shape mirrors the
plugin's `hooks/hooks.json`; `${CLAUDE_PLUGIN_ROOT}` does not resolve outside
plugin manifests, so use the absolute script path):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "compact|resume|clear|startup",
        "hooks": [
          {
            "type": "command",
            "command": "uv",
            "args": ["run", "--no-project", "--", "python",
                     "<abs-path>/skills/compaction-survival/scripts/anchor_inject.py"]
          }
        ]
      }
    ]
  }
}
```

The env gate still applies: the hook stays inert unless
`SESSION_WORKFLOW_ANCHOR_HOOKS=1` is set in the session's environment.

## Verify before trusting it

Simulate the SessionStart payload once instead of waiting for a real
compaction to find out:

```sh
echo '{"hook_event_name":"SessionStart","source":"compact","cwd":"<abs-project-path>"}' \
  | SESSION_WORKFLOW_ANCHOR_HOOKS=1 python <abs-path>/scripts/anchor_inject.py
```

Non-empty `hookSpecificOutput` JSON on stdout is the pass; 0 bytes means the
injection would silently not happen. Use an anchor containing non-ASCII text
(`→`, accented prose) as the fixture — that is the historical failure mode,
and `log.ndjson` in the anchors dir records an `anchor-inject-failed` event
when emission fails.

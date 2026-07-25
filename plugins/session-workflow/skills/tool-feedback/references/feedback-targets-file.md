# The feedback-targets file — format

The declared-file form of the bindings table (`SKILL.md` § *Registered tools*,
precedence steps 1–2). One flat TOML table per registered tool. It exists so the
binding travels between machines — a corporate box registers a different set —
without being retyped as prose in every environment's context.

The file is **plain data and self-sufficient**: absolute paths, no includes, no
tooling needed to read it, and no dependency on whatever wrote it. Anything that
generates one is invisible here, by design — a generated file that names its
generator invites a reader to go looking for it, and the binding must keep
working when it is gone.

## Shape

```toml
schema = "feedback-targets/v1"

[targets.keel]
repo = "C:/Users/grima/Documents/keel"
feedback_dir = "C:/Users/grima/Documents/keel/docs/feedback"
format_doc = "C:/Users/grima/Documents/keel/docs/feedback/README.md"
triage_template = "C:/Users/grima/Documents/keel/src/keel/templates/reflection-triage.md"
extras = [
  "reflection-triage is the registered triage template",
]

[targets.convoy]
repo = "C:/Users/grima/Documents/convoy"
feedback_dir = "C:/Users/grima/Documents/convoy/docs/feedback"
extras = [
  "include a cost/economy table (tokens/turns/$) for any engine run",
]
```

## Fields

| key | required | meaning |
|-----|----------|---------|
| `schema` (top level) | yes | `feedback-targets/v1`. An unrecognized value means *do not guess*: treat the file as unreadable, fall through to the next precedence step, and say so. |
| `[targets.<tool>]` | yes, ≥1 | One table per registered tool. The table key **is** the tool name used in reports, offers, and routing. |
| `repo` | yes | Absolute path to the tool's working tree — the manifest to read the version from, the source to ground claims against. |
| `feedback_dir` | yes | Absolute path where this tool's reports and its `INDEX.md` live. This is the *registered* dir, so it stays the recurrence baseline even when a session redirects the write. |
| `format_doc` | no | Absolute path to the format doc that is authoritative for that dir. Missing file → fall back to the skill's template and note the gap in the report. |
| `triage_template` | no | Absolute path to the tool's own triage template; `feedback-triage` follows it instead of its built-in one. |
| `extras` | no | Per-tool obligations, one string each — read and honor them exactly as the prose table's `extras` column. |

Unknown keys are ignored rather than fatal, so a newer writer does not break an
older reader. Nothing nests deeper than one table per tool.

## Reading it

- The file **declares** the targets; it does not authorize discovery. A tool
  absent from it is unregistered, and a path in it that does not exist is a
  finding to report, not a cue to go looking for the real one.
- Both binding forms carry the same fields, so nothing downstream changes with
  the source: same destination precedence, same recurrence check, same `extras`
  obligations.
- Relative paths are a malformed file, not a resolution puzzle — the writer's
  cwd is unknowable here. Report the malformed entry and fall through.

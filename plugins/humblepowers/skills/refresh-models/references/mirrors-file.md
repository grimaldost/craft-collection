# The mirror-sites bindings file

The mirror walk (step 6) needs to know which downstream copies of tier, model,
and price data exist in a given stack. A published plugin cannot know that, so
the list is a binding the operator supplies.

It used to be supplied as **prose in the operator's private global
instructions** — an external coupling no other environment reproduces, that no
tool can validate, and that has to be maintained by hand on every machine. This
file replaces that with a machine-readable file at a known path, the shape the
feedback-targets registry already proved: plain, absolute-pathed,
self-sufficient, and portable between environments.

`scripts/mirror_check.py` reads it. Everything below is what that script
enforces, so a field described here is a field with a check behind it.

## Resolution

1. `$MODEL_MIRRORS_FILE`, when set.
2. Otherwise `~/.claude/model-mirrors.toml`.
3. Neither resolves → **report the skip and proceed.** An absent file is the
   correct behaviour for a fresh environment, not a failure. Do not hunt the
   filesystem for candidate mirrors.

Case 3 is reported, never silent. On 2026-08-11 this file's mechanism shipped
and its contents were left to the operator; 25 days later the file still did not
exist, no walk had run, and two sibling estimators had carried a superseded
price the whole time. "Nothing to walk" and "no registry" must not read alike,
which is why the script prints `mirror walk SKIPPED` with the path it looked
for, and why step 6 requires that line in the changeset verbatim.

## Format

```toml
# ~/.claude/model-mirrors.toml
# Downstream copies of tier / model / price data. Absolute paths only:
# the walk runs from whatever directory the session happens to be in.

canonical = "/abs/path/to/humblepowers/skills/choosing-models/models.toml"

[[site]]
path = "/abs/path/to/engine/src/engine/core/governance.py"
symbol = "DEFAULT_TIER_MODELS"          # optional: what to look for in the file
mirrors = "tier-to-model map"           # what this copy holds
vocabulary = "tier"                     # "tier" | "family" | "api-string"
role = "fallback"                       # see below - "resolution-path" is a finding
stamp = "lineup synced"                 # the file must carry "<stamp> <last_reviewed>"
backlog = "/abs/path/to/engine/docs/backlog.md"
note = "self-contained by charter: carries a copy, never a reference back."

[[site]]
path = "/abs/path/to/method/src/method/templates/series-skeleton.md"
mirrors = "pinned tier examples"
vocabulary = "family"                   # translate, do not substitute
role = "example"
backlog = "/abs/path/to/method/docs/backlog.md"
status = "no backlog row yet"           # see the rule below

# Strings that must no longer appear anywhere. This is the catch-all arm: it is
# what finds a mirror nobody wrote down.
[[retired]]
pattern = "claude-fable-5(?![-.0-9])"   # a regex, so a successor is not a hit
reason = "superseded by claude-fable-5-1 on 2026-09-05; Fable 5 is legacy"
roots = ["/abs/path/to/engine", "/abs/path/to/harness"]

[[exclude]]
glob = "**/tasks/**"
reason = "byte-preserved eval fixture, not a live mirror"
```

### Fields

| field | required | meaning |
|---|---|---|
| `canonical` (top level) | for stamps | Absolute path to `models.toml`. Its `[meta].last_reviewed` is the one date every stamp is held against. |
| `path` | yes | Absolute path to the file holding the copy. |
| `mirrors` | yes | What the copy holds, in one phrase. |
| `vocabulary` | yes | Which words the copy speaks — see below. |
| `role` | recommended | What the copy IS — see below. |
| `symbol` | no | The identifier to find inside the file. |
| `stamp` | no | A literal prefix; the file must contain `<stamp> <canonical last_reviewed>`. |
| `backlog` | no | That repository's own backlog, where the edit gets a row. |
| `status` | no | `pending removal`, `no backlog row yet`, and similar. A site the walk should read differently than a live one. |
| `note` | no | Anything the next walk needs and would otherwise rediscover. |

`[[retired]]` takes `pattern` (a Python regex), `reason`, and `roots` (absolute
directories to search). `[[exclude]]` takes `glob` and `reason`, and the count of
files it hid is printed — an exclusion that quietly swallows work is the failure
mode it would otherwise become.

### `vocabulary` is not decoration

A mirror does not necessarily speak the same words as the canonical file.

- `tier` — the copy uses tier names (`weak`/`mid`/`strong`/`frontier`). Substitute directly.
- `family` — the copy uses family names (`haiku`/`sonnet`/`opus`/`fable`). **Translate**, do not substitute: a tier name written where a family name belongs is a silent break, and a family-keyed price table is usually unaffected by a model-id change inside that family.
- `api-string` — the copy pins a full model id. These are the copies a lineup change actually invalidates.

Family vocabulary is why the catch-all needs `[[retired]]` patterns for prices as
well as ids: a grep for the outgoing *model string* passes straight over a
family-keyed price table, and that is how a second one went unregistered until an
audit tripped over it in 2026-09.

### `role` says whether a stale copy can hurt

- `resolution-path` — this copy DECIDES what a run executes on. **The walk
  reports it as a finding, by design.** The goal state is zero of these: the
  artefact of the run carries the resolved value, and every copy is a floor.
- `fallback` — consulted only when the artefact carries nothing. Stale is
  survivable if it announces itself.
- `example` — a sample in a template or scaffold. Never resolved; wrong here
  misleads an author, it does not misroute a run.
- `prose` — documentation describing the lineup. Same blast radius as `example`.

### `stamp` is one clock, not two

The stamp is compared for **equality** with the canonical `last_reviewed`, never
for age. Two independent clocks — a horizon here and a horizon in the canonical
file — let a copy certify itself fresh while the source moved on, and the age
check then measures the stamp rather than the lineup. One date, held in both
places, cannot do that.

For the same reason a stamp records the **canonical reconciliation date**, not
the date the mirror was edited. Stamping a lineup that is already behind dates
the wrong thing.

## The rule this file exists to enforce

**A registered mirror with no row in its own repository's backlog is the failure
this file prevents.** A copy that nobody's backlog tracks drifts silently: the
walk edits it once, and the next lineup change finds it stale again with no
record of why. When a site is registered, either its `backlog` names a row or
its `status` says one is missing — and a walk that finds `status = "no backlog
row yet"` reports it as work, not as a clean site.

Sites the owning repository has already decided to delete are recorded with
`status = "pending removal"` rather than dropped, so the walk does not edit a
file that is about to disappear and does not silently forget it either.

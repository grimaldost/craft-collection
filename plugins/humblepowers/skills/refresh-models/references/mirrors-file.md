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

## Resolution

1. `$MODEL_MIRRORS_FILE`, when set.
2. Otherwise `~/.claude/model-mirrors.toml`.
3. Neither resolves → **ask once, then proceed without the walk.** An absent
   file is the correct behaviour for a fresh environment, not a failure. Do not
   hunt the filesystem for candidate mirrors.

The closing grep stays either way: after the lineup edit lands, search the
working repositories for the *outgoing* model string and report any hit as a
candidate mirror to register. That is the catch-all for mirrors nobody wrote
down.

## Format

```toml
# ~/.claude/model-mirrors.toml
# Downstream copies of tier / model / price data. Absolute paths only:
# the walk runs from whatever directory the session happens to be in.

[[site]]
path = "/abs/path/to/engine/src/engine/core/governance.py"
symbol = "DEFAULT_TIER_MODELS"          # optional: what to look for in the file
mirrors = "tier-to-model map"           # what this copy holds
vocabulary = "tier"                     # "tier" | "family" | "api-string"
backlog = "/abs/path/to/engine/docs/backlog.md"
note = "self-contained by charter: carries a copy, never a reference back."

[[site]]
path = "/abs/path/to/harness/src/harness/adapters/cli.py"
symbol = "_PRICE_PER_1K"
mirrors = "per-family price fallback"
vocabulary = "family"
backlog = "/abs/path/to/harness/docs/backlog.md"
note = "family-keyed, so a model-id change inside a family does not reach it."

[[site]]
path = "/abs/path/to/method/src/method/templates/series-skeleton.md"
mirrors = "pinned tier examples"
vocabulary = "family"                   # translate, do not substitute
backlog = "/abs/path/to/method/docs/backlog.md"
status = "no backlog row yet"           # see the rule below
```

### Fields

| field | required | meaning |
|---|---|---|
| `path` | yes | Absolute path to the file holding the copy. |
| `mirrors` | yes | What the copy holds, in one phrase. |
| `vocabulary` | yes | Which words the copy speaks — see below. |
| `symbol` | no | The identifier to find inside the file. |
| `backlog` | no | That repository's own backlog, where the edit gets a row. |
| `status` | no | `pending removal`, `no backlog row yet`, and similar. A site the walk should read differently than a live one. |
| `note` | no | Anything the next walk needs and would otherwise rediscover. |

### `vocabulary` is not decoration

A mirror does not necessarily speak the same words as the canonical file.

- `tier` — the copy uses tier names (`weak`/`mid`/`strong`/`frontier`). Substitute directly.
- `family` — the copy uses family names (`haiku`/`sonnet`/`opus`/`fable`). **Translate**, do not substitute: a tier name written where a family name belongs is a silent break, and a family-keyed price table is usually unaffected by a model-id change inside that family.
- `api-string` — the copy pins a full model id. These are the copies a lineup change actually invalidates.

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

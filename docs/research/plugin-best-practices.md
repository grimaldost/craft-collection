# Claude Code Plugin Best Practices (research, 2026-06)

Authoritative reference distilled from the official docs. Sources at the bottom.

## Plugin structure

Only `plugin.json` lives in `.claude-plugin/`; **all other component dirs are at
the plugin root**:

```text
my-plugin/
  .claude-plugin/plugin.json
  skills/<skill>/SKILL.md (+ references/ scripts/ assets/)
  commands/*.md            # legacy; prefer skills/ for new work
  agents/*.md
  hooks/hooks.json
  .mcp.json  .lsp.json
  README.md  CHANGELOG.md  LICENSE
```

## plugin.json

Required: `name` (kebab-case; namespaces skills as `/plugin:skill`). Recommended:
`version` (semver — **must bump per release or users never update**; omit to use
the commit SHA), `description`, `displayName`, `author`, `repository`, `license`,
`keywords`. Path fields: `skills` (adds to the default `skills/` scan),
`commands`/`agents`/`outputStyles` (replace defaults), `hooks`/`mcpServers`/
`lspServers` (own merge rules). `userConfig` exposes `${user_config.KEY}` to
MCP/hook configs and `CLAUDE_PLUGIN_OPTION_<KEY>` env vars; `defaultEnabled:false`
installs disabled.

## Skills

`SKILL.md` frontmatter that matters: `name`, `description` (combined with
`when_to_use`, **capped at 1,536 chars** — key use case first), `allowed-tools` /
`disallowed-tools`, `disable-model-invocation` (manual-only), `user-invocable`,
`model`, `effort`, `context: fork` + `agent`, `paths` (auto-load on matching
files), `shell`. Substitutions: `$ARGUMENTS`, `$1`/`$N`, `$name`,
`${CLAUDE_SKILL_DIR}`, `${CLAUDE_SESSION_ID}`. **Keep the body < 500 lines**; move
detail to `references/` (loaded on demand), executables to `scripts/`, templates
to `assets/`. Reference files one level deep with relative links.

## Hooks

`hooks/hooks.json` shape: `{ "hooks": { "<Event>": [ { "matcher": "...",
"hooks": [ { "type": "command", "command": "...", "args": [...] } ] } ] } }`.
Events include `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`,
`Stop`/`SubagentStop`, `PreCompact`, `SessionEnd`, and many more. Matchers:
`"*"`/empty = all; `Bash|Edit` = exact/pipe list; otherwise JS regex. Hook types:
`command`, `http`, `mcp_tool`, `prompt`, `agent`. **Exit codes:** 0 ok (stdout
parsed for JSON), **2 blocking** (stderr fed to Claude), other non-blocking. JSON
output can set `permissionDecision`, `decision`, `systemMessage`, etc. Path vars:
`${CLAUDE_PLUGIN_ROOT}`, `${CLAUDE_PLUGIN_DATA}` (persists across updates),
`${CLAUDE_PROJECT_DIR}`. Prefer exec form (`command` + `args`) over shell form;
always quote path vars in shell form.

## Agents in plugins

`agents/*.md` frontmatter: `name`, `description`, `model`, `effort`, `maxTurns`,
`tools`/`disallowedTools`, `skills`, `memory`, `background`, `isolation:
"worktree"` (the only supported value; hooks/mcpServers/permissionMode not
supported in plugin agents).

## Versioning & distribution

Explicit `version` (bump every release) for published plugins; omit it for
commit-SHA-per-push during active dev. Dev loop: `claude --plugin-dir ./my-plugin`
then `/reload-plugins`. Validate: `claude plugin validate ./my-plugin --strict`.
Inspect cost: `claude plugin details <name>`. Distribute via the community
marketplace (`anthropics/claude-plugins-community`), the official marketplace, or
a private git marketplace (`/plugin marketplace add owner/repo`).

## marketplace.json

Lives at repo root `.claude-plugin/marketplace.json`. Required: `name` (kebab),
`owner`, `plugins[]` (each needs `name` + `source`). High-value optional fields:
`description`, `displayName`, `version`, `keywords`, `category`, `tags`,
`homepage`, `license`. `metadata.pluginRoot: "./plugins"` lets `source` be a bare
name. Pin with `source: { source: "github", repo, ref, sha }`.

## Quality guidance

Progressive disclosure (metadata → SKILL.md → bundled files); description budget
1,536 chars, key use first; SKILL.md < 500 lines; reference docs instead of
inlining; test triggering with `/skill-creator`; lifecycle hooks (SessionStart
setup, PostToolUse validation, SessionEnd cleanup).

## Sources

- https://code.claude.com/docs/en/plugins
- https://code.claude.com/docs/en/plugins-reference
- https://code.claude.com/docs/en/skills
- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/plugin-marketplaces
- https://code.claude.com/docs/en/discover-plugins

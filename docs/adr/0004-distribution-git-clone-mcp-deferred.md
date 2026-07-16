# ADR-0004 — Distribution off-CC: git clone; MCP server deferred

- **Status:** Accepted
- **Date:** 2026-07-16

## Context

Claude Code consumers install and update through the marketplace
(`.claude-plugin/marketplace.json` + per-plugin `version` bumps). No other
harness reads that channel. Off-CC consumers need an install path, an update
path, and a version signal — without adding a second packaging system to
maintain.

## Decision

The off-CC distribution channel is a plain `git clone` of this repository;
update is `git pull`. The generated `AGENTS.md` (ADR-0002) makes a fresh clone
immediately consumable. `plugin.json` remains the single version source; the
README gains an installation matrix (per-harness: what to clone, what to point
the agent at, what enforcement tier applies per ADR-0003). An MCP server that
would expose the utility scripts as tools and the skills as resources is
**deferred**: it is recorded as the named revisit path, triggered when a
concrete consumer that cannot read files (or a user request) demands it.

## Alternatives considered

- **Build the MCP server now** — rejected for this wave: real build/maintain
  cost, context cost of tool schemas, and no identified consumer today; nothing
  in this decision blocks adding it later as a complement.
- **Publish to third-party skill/plugin registries** — rejected: per-registry
  packaging and release work, immature targets, and clone-plus-index already
  covers their consumers.
- **Versioned release tarballs** — rejected: adds release ceremony without
  solving anything `git pull` does not.

## Consequences

- Off-CC consumers track `main` (or pin a SHA themselves); there is no
  per-plugin update granularity outside CC — accepted trade-off, documented in
  the installation matrix.
- The MCP revisit trigger is explicit, so the deferral cannot silently become
  a permanent gap.

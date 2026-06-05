# Security Policy

## Supported versions

This collection is actively maintained on `main`. Security fixes are applied to the
latest released line of each plugin; older tags are not patched.

| Plugin                 | Version | Supported |
| ---------------------- | ------- | --------- |
| engineering-discipline | 0.1.x   | ✅        |
| session-workflow       | 0.1.x   | ✅        |

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Use GitHub's private reporting instead: go to the repository's **Security** tab →
**Report a vulnerability** (GitHub Private Vulnerability Reporting). If you can't use
that, email **grimaldosj93@gmail.com** with the details.

Please include:

- the affected skill, hook, or script (and file path);
- a description of the issue and its impact;
- steps to reproduce or a proof of concept, if you have one.

This is a solo-maintained project, so responses are best-effort: expect an
acknowledgement within about a week, and please allow reasonable time for a fix
before any public disclosure. Coordinated disclosure is appreciated.

## Scope

The security-relevant surface of this repo is **code that executes**, not the
advisory text inside skills:

- **Hooks** (`PreToolUse` / `PostToolUse` / `Stop` / `SessionStart`) that run on a
  developer's machine during a Claude Code session.
- **Scripts** under each skill's `scripts/` and the `scripts/` and `evals/harness/`
  directories.
- **CI workflows** under `.github/workflows/`.

Relevant reports include things like a hook or script that could run unintended
commands, leak data, or be exploited via crafted input; an injection path in a
workflow; or insecure handling of credentials. Guidance and documentation content
(the prose a skill teaches) is out of scope for this policy.

These plugins run locally with the same privileges as your shell — review any hook
or script before enabling it, exactly as you would any third-party tooling.

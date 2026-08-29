#!/usr/bin/env python3
"""A PR that touches a plugin bumps its version and logs it, or declares why not.

CONTRIBUTING's release rule -- Claude Code only pulls a plugin update when its
`plugin.json` version changes -- existed only as prose, and it failed the day
it mattered: two behavior fixes shipped hours after the 0.23.0 bump under an
unchanged version, so no installed copy could receive them and one version
label named two different trees. This check makes the rule mechanical.

For every `plugins/<p>/` with changes in the diff against the merge base
(that plugin's own `CHANGELOG.md` and `README.md` excluded), the tree at HEAD
must satisfy BOTH:

  * `plugins/<p>/.claude-plugin/plugin.json` `version` INCREASED over the
    merge-base version (a plugin absent at the base is new, which counts);
  * that version is the changelog's top `## [X.Y.Z] - YYYY-MM-DD` heading
    (a leading `## [Unreleased]` section is skipped, not satisfying).

OR the range must carry, in some commit, the git trailer

    Release-note: none (<reason>)

parsed as a trailer (`%(trailers:...)`), so prose QUOTING the convention --
this file does, CONTRIBUTING does -- cannot waive anything.

for a change that genuinely ships nothing an installed copy could notice. The
declaration waives the whole PR and is reviewed as prose, not parsed further.

Usage: python scripts/check_release_discipline.py [--base REF] [--repo DIR]

`--base` defaults to origin/main; CI passes the PR's base branch. Exit 0 clean,
1 on findings, 2 when git cannot answer (unknown ref, not a repository) --
a gate that cannot see the diff must say so rather than pass.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

MANIFEST = '.claude-plugin/plugin.json'
CHANGELOG = 'CHANGELOG.md'
# Directly under plugins/<p>/, these never require a release on their own: the
# release record itself, and the plugin's front page.
EXEMPT = ('CHANGELOG.md', 'README.md')
HEADING = re.compile(r'^## \[(?P<version>[^\]]+)\] - \d{4}-\d{2}-\d{2}\s*$')
DECLARATION = re.compile(r'^none \(.+\)$')


def declared(trailer_values: str) -> bool:
    """Whether any `Release-note:` trailer value in the range reads
    `none (<reason>)`. Takes the output of
    `git log --format=%(trailers:key=Release-note,valueonly)` -- git's own
    trailer parser -- so a commit body merely quoting the convention is not a
    declaration. Pure."""
    return any(DECLARATION.match(line.strip()) for line in trailer_values.splitlines())


def touched_plugins(changed: list[str]) -> list[str]:
    """Plugin names with non-exempt changes among `changed` paths. Pure."""
    out: set[str] = set()
    for path in changed:
        parts = path.split('/')
        if len(parts) < 3 or parts[0] != 'plugins':
            continue
        if len(parts) == 3 and parts[2] in EXEMPT:
            continue
        out.add(parts[1])
    return sorted(out)


def top_heading_version(changelog: str | None) -> str | None:
    """The version in the changelog's first release heading, or None when that
    heading (or the whole file) does not parse. A leading `## [Unreleased]`
    section is skipped -- legitimate to keep, never satisfying. Pure."""
    if changelog is None:
        return None
    for line in changelog.splitlines():
        if not line.startswith('## '):
            continue
        if line.strip() == '## [Unreleased]':
            continue
        match = HEADING.match(line)
        return match.group('version') if match else None
    return None


def _version_tuple(version: str) -> tuple[int, ...] | None:
    """`'1.2.3' -> (1, 2, 3)`, or None for anything not dotted integers. Pure."""
    try:
        return tuple(int(part) for part in version.split('.'))
    except ValueError:
        return None


def audit(plugins: dict[str, dict]) -> list[str]:
    """Findings for `plugins`: name -> {base_version, head_version, top}. Pure."""
    findings: list[str] = []
    for name, state in sorted(plugins.items()):
        head = state.get('head_version')
        base = state.get('base_version')
        top = state.get('top')
        if head is None:
            if base is not None:
                findings.append(
                    f'{name}: plugins/{name}/{MANIFEST} is gone at HEAD (was {base}) -- '
                    'retiring a plugin is a release decision; declare '
                    '"Release-note: none (<reason>)" to say so'
                )
            else:
                findings.append(
                    f'{name}: plugins/{name}/{MANIFEST} is missing or has no version at HEAD'
                )
            continue
        if base is not None and head == base:
            findings.append(
                f'{name}: files changed but the version is still {head} -- bump '
                f'plugins/{name}/{MANIFEST} (or declare "Release-note: none (<reason>)" '
                'in a commit trailer)'
            )
        elif base is not None:
            head_t, base_t = _version_tuple(head), _version_tuple(base)
            if head_t is not None and base_t is not None and head_t <= base_t:
                findings.append(
                    f'{name}: version went {base} -> {head}, which does not increase -- '
                    'a release moves forward'
                )
        if top != head:
            findings.append(
                f'{name}: plugins/{name}/{CHANGELOG} top heading must be '
                f'"## [{head}] - YYYY-MM-DD" (found: {top or "no parseable heading"})'
            )
    return findings


def _git(repo: Path, *args: str) -> str:
    """Run git in `repo` and return stdout. GIT_* is scrubbed so `-C` is
    authoritative -- git exports the repository location into every hook it
    runs, and an ambient GIT_DIR would answer about the outer repository."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(repo), *args],  # noqa: S607 - git resolved from PATH
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        timeout=60,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} failed: {proc.stderr.strip()}')
    return proc.stdout


def _show(repo: Path, ref: str, path: str) -> str | None:
    try:
        return _git(repo, 'show', f'{ref}:{path}')
    except RuntimeError:
        return None


def _manifest_version(text: str | None) -> str | None:
    if text is None:
        return None
    try:
        version = json.loads(text).get('version')
    except ValueError:
        return None
    return version if isinstance(version, str) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--base', default='origin/main', help='ref to diff against (merge base)')
    parser.add_argument('--repo', default='.', help='repository to check (default: cwd)')
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()

    try:
        merge_base = _git(repo, 'merge-base', args.base, 'HEAD').strip()
        # --no-renames: rename detection reports only the destination path, so
        # a file moved OUT of a plugin would read as not touching it.
        changed = _git(repo, 'diff', '--name-only', '--no-renames', merge_base, 'HEAD').splitlines()
        trailer_values = _git(
            repo, 'log', '--format=%(trailers:key=Release-note,valueonly)', f'{merge_base}..HEAD'
        )
    except (RuntimeError, OSError, subprocess.SubprocessError) as err:
        print(f'release discipline: cannot read the diff: {err}')
        return 2

    plugins = touched_plugins([line.strip() for line in changed if line.strip()])
    if not plugins:
        print('release discipline: no plugin files touched')
        return 0

    if declared(trailer_values):
        print(
            'release discipline: "Release-note: none (...)" declared for '
            + ', '.join(plugins)
            + ' -- the reviewer judges the reason'
        )
        return 0

    state = {
        name: {
            'base_version': _manifest_version(
                _show(repo, merge_base, f'plugins/{name}/{MANIFEST}')
            ),
            'head_version': _manifest_version(_show(repo, 'HEAD', f'plugins/{name}/{MANIFEST}')),
            'top': top_heading_version(_show(repo, 'HEAD', f'plugins/{name}/{CHANGELOG}')),
        }
        for name in plugins
    }
    findings = audit(state)
    for finding in findings:
        print(f'RELEASE: {finding}')
    if findings:
        return 1
    print(f'release discipline: {len(plugins)} plugin(s) bumped and logged')
    return 0


if __name__ == '__main__':
    sys.exit(main())

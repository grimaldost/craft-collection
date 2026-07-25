#!/usr/bin/env python3
"""Fill the act-hint record's frozen coordinates and material SHAs -- mechanically.

A pre-registration freeze is a two-stage handoff because a commit cannot name its own
SHA. This module is the mechanical half of that handoff, so the orchestrator's job is
two commits and no judgement:

  stage 0 (before the freeze commit)   python freeze_fill.py
      Computes the SHA256 of every frozen material and writes it into `materials`,
      into both outcomes' `verifier.hash`, and into `oracle_validation.sha256`. This
      MUST happen before stage 1: `verifier.hash` sits inside ER-PREREG's frozen
      subset, so a placeholder committed at stage 1 and filled at stage 2 would read
      as drift from the frozen plan.

  stage 2 (after the freeze commit)    python freeze_fill.py --freeze-sha <SHA>
      Replaces the freeze-fill region with the real `plan_frozen_at` block -- the
      commit, the record's repo-relative path AT that commit (git show does not
      follow renames), and the commit's own committer date -- then re-renders
      report.md and re-runs validate.py and the drift gate.

It is DETERMINISTIC (the timestamp comes from the commit, never the wall clock) and
IDEMPOTENT (it rewrites a delimited region and named values, never appends), so
running it twice with the same SHA is a no-op. It edits the record TEXTUALLY rather
than round-tripping it through a YAML dumper, so the authored comments survive and
the stage-1 to stage-2 diff is readable.

A material whose SHA is already filled and DISAGREES with the file on disk is a
FAILURE, not a silent rewrite: that is a post-freeze edit to an experimental
material, which is exactly what hashing them into the record exists to detect.

Stdlib + PyYAML. Python 3.13+.

    python freeze_fill.py [--record record.yaml] [--freeze-sha <SHA>] [--check]
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / 'plugins' / 'experiment-discipline' / 'skills' / 'experiment-rigor' / 'scripts'
RECORD_PATH = HERE / 'record.yaml'

REGION_START = '# --- freeze fill region (managed by freeze_fill.py; do not hand-edit) ---'
REGION_END = '# --- end freeze fill region ---'

# material key -> (path relative to the record, the placeholder token it ships with).
# The tokens are distinct and no token is a prefix of another, so filling them is an
# unambiguous string substitution rather than a line-position guess.
MATERIALS: dict[str, tuple[str, str]] = {
    'bank': ('bank.json', 'PENDING_SHA256_BANK'),
    'rules_control': ('rules/control.json', 'PENDING_SHA256_RULES_CONTROL'),
    'rules_narrow': ('rules/narrow.json', 'PENDING_SHA256_RULES_NARROW'),
    'rules_wide': ('rules/wide.json', 'PENDING_SHA256_RULES_WIDE'),
    'rules_inert': ('rules/inert.json', 'PENDING_SHA256_RULES_INERT'),
    'firing_table': ('firing_table.json', 'PENDING_SHA256_FIRING_TABLE'),
    'oracle': ('verify.py', 'PENDING_SHA256_ORACLE_VERIFY'),
    'oracle_patterns': ('oracle_patterns.json', 'PENDING_SHA256_ORACLE_PATTERNS'),
    'oracle_labels': ('oracle_labels.json', 'PENDING_SHA256_ORACLE_LABELS'),
}


def sha256_of(path: str | Path) -> str:
    """The SHA256 of a material, newline-normalized.

    Normalized because the repo's line endings are not stable across checkouts on
    Windows and a hash that changes with a checkout would raise a false post-freeze
    edit on every clone -- an integrity check nobody can keep green stops being one.
    """
    data = Path(path).read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def material_hashes(record_dir: str | Path = HERE) -> dict[str, str]:
    base = Path(record_dir)
    return {key: sha256_of(base / rel) for key, (rel, _token) in MATERIALS.items()}


def stated_hashes(record: dict[str, Any]) -> dict[str, str | None]:
    materials = record.get('materials') or {}
    return {
        key: (materials.get(key) or {}).get('sha256')
        for key in MATERIALS
        if isinstance(materials.get(key), dict) or key in materials
    }


def _is_placeholder(value: object, token: str) -> bool:
    return value is None or str(value) == token


def fill_materials(
    text: str, record: dict[str, Any], computed: dict[str, str]
) -> tuple[str, list[str]]:
    """Substitute every material SHA. Returns (new text, failures).

    A failure is a slot whose stated SHA is neither the placeholder nor the computed
    value -- a material edited after it was hashed into the record.
    """
    failures: list[str] = []
    materials = record.get('materials') or {}
    # Longest token first: no token is a prefix of another, but ordering the
    # substitutions makes that independent of the table's spelling.
    for key in sorted(MATERIALS, key=lambda k: -len(MATERIALS[k][1])):
        rel, token = MATERIALS[key]
        want = computed[key]
        stated = (materials.get(key) or {}).get('sha256')
        if _is_placeholder(stated, token):
            text = text.replace(token, want)
            continue
        if str(stated) != want:
            failures.append(
                f'{key} ({rel}): the record states {stated} but the file on disk hashes to '
                f'{want} -- a post-freeze edit to a frozen material'
            )
    return text, failures


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', '-C', str(REPO), *args],  # noqa: S607 - git resolved from PATH
        capture_output=True,
        text=True,
    )


def commit_date(sha: str) -> str:
    proc = _git('show', '-s', '--format=%cI', sha)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise SystemExit(f'freeze_fill: commit {sha} is not in this repository')
    return proc.stdout.strip()


def repo_relpath(path: str | Path) -> str:
    proc = _git('rev-parse', '--show-toplevel')
    top = Path(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else REPO
    return Path(path).resolve().relative_to(top.resolve()).as_posix()


def frozen_block(sha: str, relpath: str, timestamp: str) -> str:
    """The generated plan_frozen_at region. Quoted timestamp so PyYAML keeps it a
    string rather than turning it into a datetime the drift digest would re-render."""
    return (
        f'{REGION_START}\n'
        '# Generated by freeze_fill.py from the stage-1 freeze commit. The path is the\n'
        '# record path AT that commit -- `git show <commit>:<path>` does not follow renames,\n'
        '# so this value is historical and is never updated when the record moves.\n'
        'plan_frozen_at:\n'
        f'  commit: {sha}\n'
        f'  path: {relpath}\n'
        f"  timestamp: '{timestamp}'\n"
        f'{REGION_END}\n'
    )


def replace_region(text: str, block: str) -> str:
    start = text.index(REGION_START)
    end = text.index(REGION_END, start) + len(REGION_END) + 1
    return text[:start] + block + text[end:]


def fill(
    record_path: str | Path = RECORD_PATH, freeze_sha: str | None = None
) -> tuple[str, list[str]]:
    """The pure-ish core: return (new record text, failures). Reads the materials from
    disk and, when a SHA is given, the commit's date from git. Writes nothing."""
    path = Path(record_path)
    text = path.read_text(encoding='utf-8').replace('\r\n', '\n')
    record = yaml.safe_load(text)
    computed = material_hashes(path.parent)
    text, failures = fill_materials(text, record, computed)
    if freeze_sha:
        sha = _git('rev-parse', freeze_sha).stdout.strip() or freeze_sha
        text = replace_region(text, frozen_block(sha, repo_relpath(path), commit_date(sha)))
    return text, failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='Fill the act-hint record freeze coordinates.')
    ap.add_argument('--record', default=str(RECORD_PATH), help='path to record.yaml')
    ap.add_argument(
        '--freeze-sha',
        default=None,
        help='the stage-1 freeze commit; omit before the commit exists (materials only)',
    )
    ap.add_argument('--check', action='store_true', help='report what would change; write nothing')
    args = ap.parse_args(argv)

    path = Path(args.record).resolve()
    text, failures = fill(path, args.freeze_sha)
    for line in failures:
        print(f'FROZEN-MATERIAL MISMATCH: {line}')
    if failures:
        return 1

    current = path.read_text(encoding='utf-8').replace('\r\n', '\n')
    changed = text != current
    if args.check:
        print(f'{"WOULD CHANGE" if changed else "UP TO DATE"} {path}')
        return 0
    if changed:
        path.write_text(text, encoding='utf-8', newline='\n')
    print(f'{"filled" if changed else "already filled"} {path}')

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    import render
    import validate

    record = yaml.safe_load(text)
    report_path = path.parent / 'report.md'
    report_path.write_text(render.render_report(record), encoding='utf-8', newline='\n')
    print(f'rendered {report_path}')

    report = validate.run_checks(record, path)
    for finding in report.findings:
        tag = finding.code if finding.level == 'FAIL' else f'{finding.level} [{finding.code}]'
        print(f'{tag}: {finding.message}')
    drift = render.check_drift(path)
    if drift is not None:
        print(f'DRIFT: {drift}')
    print(
        f'{len(report.failures)} failure(s), {len(report.warnings)} warning(s), '
        f'{"drift" if drift else "no drift"}'
    )
    if not args.freeze_sha:
        print(
            'NOTE: no --freeze-sha given, so plan_frozen_at is still absent. ER-ANCHOR is '
            'EXPECTED to fail and ER-PREREG to warn until the stage-1 commit exists; re-run '
            'with --freeze-sha <SHA> afterwards and both clear.'
        )
    return 0


if __name__ == '__main__':
    sys.exit(main())

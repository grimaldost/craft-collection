#!/usr/bin/env python3
"""Checks of the README's account of policy version 2, packs and the doctor's rules.

Contract under test:
- the README holds one fenced TOML block that is a complete example `pack.toml`
  and one that is a complete version 2 policy with a `[[checker]]` table, and
  both load: the pack through `read_pack`, the policy through `load_policy`
  once its `sha256` is the hash of a stub at its `file` path;
- it holds one fenced command line that starts with `kit policy build` and
  gives the uv pack's folder to `--pack` as `harness-kit/packs/uv`; run on that
  folder, it writes a policy that loads;
- it names the three results, the keys `check`, `sha256` and `budget_ms`, the
  500 ms total of one judgement and the `rules` section of the doctor;
- under the heading "What this slice does not do" it states the four limits of
  the second slice, and the sentence naming `kit policy build` and its exit 64
  stays on one line.

Stdlib-runnable: `python test_readme_rules.py`.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
REPO = KIT_ROOT.parent
README = KIT_ROOT / 'README.md'
PORTABILITY = REPO / 'docs' / 'portability.md'
sys.path.insert(0, str(KIT_ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness_kit import packs  # noqa: E402
from harness_kit.policy import load_policy  # noqa: E402
from kit_fixtures import SAMPLE_POLICY, SRC, run_module  # noqa: E402

STUB = b'def check(act, observation):\n    return {"result": "no-match"}\n'
FENCE = re.compile(r'^```(\w*)\n(.*?)^```$', re.MULTILINE | re.DOTALL)
HEADING = '## What this slice does not do'
LIMITS = (
    "a rule's refusal is feedback",
    "the uv rule's preventing layer is pip's own setting and is not installed or checked by the kit",
    'the kit is not wired into a daily session',
    "the doctor's `tested` for a rule comes from the contract and does not see a core "
    'that has gone missing since',
)


def _text() -> str:
    return README.read_text(encoding='utf-8')


def _blocks(lang: str) -> list[str]:
    return [body for tag, body in FENCE.findall(_text()) if tag == lang]


def _commands() -> list[str]:
    return [
        body.strip()
        for tag, body in FENCE.findall(_text())
        if tag in ('', 'sh', 'bash') and body.lstrip().startswith('kit policy build')
    ]


def _section(heading: str) -> str:
    match = re.search(rf'^{re.escape(heading)}\n(.*?)(?=^## |\Z)', _text(), re.M | re.S)
    assert match, f'no section {heading!r}'
    return match.group(1)


def test_one_example_pack_toml_that_reads_as_a_pack():
    found = [b for b in _blocks('toml') if re.search(r'^pack = 1$', b, re.M)]
    assert len(found) == 1, len(found)
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / 'pack.toml').write_text(found[0], encoding='utf-8')
        data = __import__('tomllib').loads(found[0])
        for entry in data['checker']:
            target = folder / entry['file']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(STUB)
        pack = packs.read_pack(folder)
        assert pack.rules and pack.checkers


def test_one_example_policy_with_a_checker_table_that_loads():
    found = [b for b in _blocks('toml') if re.search(r'^version = 2$', b, re.M)]
    assert len(found) == 1, len(found)
    assert '[[checker]]' in found[0] and '[[rule]]' in found[0]
    assert len(_blocks('toml')) == 2, len(_blocks('toml'))
    data = __import__('tomllib').loads(found[0])
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        text = found[0]
        for entry in data['checker']:
            target = folder / entry['file']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(STUB)
            text = text.replace(entry['sha256'], hashlib.sha256(STUB).hexdigest())
        (folder / 'policy.toml').write_text(text, encoding='utf-8')
        policy = load_policy(folder / 'policy.toml')
        assert policy.checkers and policy.rules


def test_one_build_command_on_the_uv_pack_gives_a_policy_that_loads():
    found = _commands()
    assert len(found) == 1, found
    assert '\n' not in found[0], found[0]
    args = shlex.split(found[0])[3:]
    assert args[args.index('--pack') + 1] == 'harness-kit/packs/uv', args
    with tempfile.TemporaryDirectory() as td:
        base = Path(td) / 'base.toml'
        base.write_text(SAMPLE_POLICY, encoding='utf-8')
        out = Path(td) / 'out.toml'
        args[args.index('--base') + 1] = str(base)
        args[args.index('--out') + 1] = str(out)
        args[args.index('--pack') + 1] = str(REPO / 'harness-kit' / 'packs' / 'uv')
        env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
        env['PYTHONPATH'] = str(SRC)
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, '-m', 'harness_kit', 'policy', 'build', *args],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        assert load_policy(out).checkers


def test_readme_names_the_checker_contract():
    text = _text()
    for word in ('match', 'no-match', 'cannot-tell', 'check', 'sha256', 'budget_ms', '500 ms'):
        assert word in text, word
    for word in ('`check`', '`sha256`', '`budget_ms`', '`match`', '`no-match`', '`cannot-tell`'):
        assert word in text, word
    assert re.search(r'^## Reading `kit doctor`', text, re.M)
    assert '`rules`' in text


def test_the_four_limits_sit_under_the_heading_each_on_one_line():
    section = _section(HEADING)
    lines = section.splitlines()
    for limit in LIMITS:
        assert any(limit in line for line in lines), limit


def test_the_policy_build_sentence_stays_on_one_line():
    lines = [ln for ln in _text().splitlines() if '`kit policy build' in ln and 'exits 64' in ln]
    assert lines, 'the sentence naming kit policy build and its exit 64 is split or gone'


def test_portability_page_points_at_packs():
    text = PORTABILITY.read_text(encoding='utf-8')
    assert re.search(r'\bpacks?\b', text) and 'harness-kit/README.md' in text


if __name__ == '__main__':
    run_module(globals(), 'readme rules')

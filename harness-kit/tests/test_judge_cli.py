#!/usr/bin/env python3
"""Checks of `kit judge [--policy PATH]` end to end, and of the core's harness-free text.

Contract under test:
- one event as JSON on stdin, one verdict as one line of ASCII JSON on stdout,
  exit 0 whenever a verdict was printed;
- `--policy` falls back to `KIT_POLICY`; no policy, a missing file or one that
  does not load is an unreadable policy, judged `unknown`;
- input that is not one valid event (bad JSON, empty, duplicate keys, bytes that
  are not UTF-8) is judged `unknown`;
- non-ASCII input under a cp1252 stdout still prints a parsable ASCII verdict;
- no `.py` file of the package outside `shells/` and `harnesses/` names a key of
  any harness's payload.

Stdlib-runnable: `python test_judge_cli.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from kit_fixtures import SAMPLE_POLICY, SRC, event, run_module, write_event

PACKAGE = SRC / 'harness_kit'


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    env.update(extra)
    return env


def _judge(stdin: bytes, *args: str, **env: str) -> dict:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', 'judge', *args],
        input=stdin,
        capture_output=True,
        env=_env(**env),
        timeout=60,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    out = proc.stdout
    assert out.isascii(), out
    lines = out.decode('ascii').splitlines()
    assert len(lines) == 1, out
    assert out.endswith(b'\n'), out
    verdict = json.loads(lines[0])
    assert list(verdict)[:2] == ['kit_verdict', 'verdict'], verdict
    assert len(verdict) == 10, verdict
    return verdict


def _ev(ev: dict) -> bytes:
    return json.dumps(ev).encode('utf-8')


def _policy_file(td: str, text: str = SAMPLE_POLICY, name: str = 'policy.toml') -> Path:
    path = Path(td) / name
    path.write_bytes(text.encode('utf-8'))
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_judge_prints_an_allow_for_an_unrelated_act():
    with tempfile.TemporaryDirectory() as td:
        policy = _policy_file(td)
        v = _judge(_ev(event()), '--policy', str(policy))
        assert v['verdict'] == 'allow', v
        assert v['governed'] is False and v['rule'] is None, v
        assert v['policy_sha256'] == _sha(policy), v
        assert (v['layer'], v['run_id'], v['launched']) == ('cli', None, False), v


def test_judge_denies_on_a_matching_deny_rule():
    with tempfile.TemporaryDirectory() as td:
        policy = _policy_file(td)
        ev = event(origin='child', **{'observation.origin': 'observed'})
        ev['act']['command'] = 'cp x ~/.claude/settings.json'
        v = _judge(_ev(ev), '--policy', str(policy))
        assert (v['verdict'], v['effect'], v['rule']) == ('deny', 'deny', 'no-config-write'), v


def test_judge_falls_back_to_kit_policy_and_the_flag_wins():
    with tempfile.TemporaryDirectory() as td:
        good = _policy_file(td)
        bad = _policy_file(td, 'version = 2\n', 'bad.toml')
        v = _judge(_ev(event()), KIT_POLICY=str(good))
        assert v['verdict'] == 'allow' and v['policy_sha256'] == _sha(good), v
        v = _judge(_ev(event()), '--policy', str(good), KIT_POLICY=str(bad))
        assert v['verdict'] == 'allow', v
        v = _judge(_ev(event()), KIT_POLICY=str(bad))
        assert v['verdict'] == 'unknown', v


def test_judge_with_no_policy_is_unknown():
    v = _judge(_ev(event()))
    assert (v['verdict'], v['effect'], v['governed'], v['rule']) == ('unknown', 'deny', True, None)
    assert v['policy_sha256'] is None, v
    v = _judge(_ev(event()), KIT_POLICY='')
    assert v['verdict'] == 'unknown', v


def test_judge_with_an_unreadable_policy_is_unknown():
    with tempfile.TemporaryDirectory() as td:
        v = _judge(_ev(event()), '--policy', str(Path(td) / 'absent.toml'))
        assert (v['verdict'], v['governed'], v['policy_sha256']) == ('unknown', True, None), v
        rule = '[[rule]]\nid = "r"\neffect = "deny"\ngoverned = true\nkinds = ["shell"]\n'
        bad = _policy_file(td, 'version = 1\n' + rule + 'command_regex = "("\n', 'bad.toml')
        v = _judge(_ev(event()), '--policy', str(bad))
        assert (v['verdict'], v['effect'], v['rule']) == ('unknown', 'deny', None), v
        assert v['policy_sha256'] == _sha(bad), v


def test_judge_with_input_that_is_not_one_valid_event_is_unknown():
    dup = _ev(event())[:-1] + b', "origin": "child"}'
    inputs = {
        'empty': b'',
        'not json': b'{"kit_event": 1,',
        'array': b'[]',
        'duplicate key': dup,
        'not utf-8': b'{"kit_event": 1, "x": "\xff"}',
        'owner': _ev(event(origin='owner')),
        'empty observed command': _ev(event(**{'act.command': ''})),
        'huge integer': b'{"kit_event": 1' + b'0' * 5000 + b'}',
        'deep nesting': b'[' * 100000 + b']' * 100000,
        'NaN': b'{"kit_event": NaN}',
    }
    with tempfile.TemporaryDirectory() as td:
        policy = _policy_file(td)
        for label, data in inputs.items():
            v = _judge(data, '--policy', str(policy))
            assert (v['verdict'], v['governed'], v['rule']) == ('unknown', True, None), (label, v)


def test_non_ascii_input_under_a_cp1252_stdout_prints_an_ascii_verdict():
    rule = (
        '[[rule]]\nid = "régle"\neffect = "deny"\ngoverned = true\nkinds = ["shell"]\n'
        'command_regex = "café"\nreason = "pas de café 中"\n'
    )
    with tempfile.TemporaryDirectory() as td:
        policy = _policy_file(td, 'version = 1\n' + rule)
        ev = event(**{'act.command': 'echo café 中文 \U0001f600', 'act.cwd': '/w/é'})
        v = _judge(_ev(ev), '--policy', str(policy), PYTHONIOENCODING='cp1252')
        assert (v['verdict'], v['rule']) == ('deny', 'régle'), v
        assert v['reason'] == 'pas de café 中', v
        raw = json.dumps(ev, ensure_ascii=False).encode('utf-8')
        v = _judge(raw, '--policy', str(policy), PYTHONIOENCODING='cp1252')
        assert v['verdict'] == 'deny', v
        bad = event(**{'act.kind': 'café'})
        v = _judge(_ev(bad), '--policy', str(policy), PYTHONIOENCODING='cp1252')
        assert v['verdict'] == 'unknown', v


def test_a_write_event_is_judged_by_its_paths():
    with tempfile.TemporaryDirectory() as td:
        policy = _policy_file(td)
        v = _judge(_ev(write_event(['/w/.claude/settings.json'])), '--policy', str(policy))
        assert (v['verdict'], v['rule']) == ('unknown', 'no-config-write'), v
        v = _judge(_ev(write_event(['/w/notes.md'])), '--policy', str(policy))
        assert v['verdict'] == 'allow', v


# Built from parts so this file does not itself carry the words it looks for.
_HARNESS_KEYS = (
    'hook_event' + '_name',
    'tool' + '_input',
    'tool' + '_name',
    'hookSpecific' + 'Output',
    'permission' + 'Decision',
    'session' + 'ID',
    'execute' + '.before',
    'updated' + 'Input',
)


def _harness_shape_hits(package: Path) -> list[str]:
    hits = []
    for path in sorted(package.rglob('*.py')):
        rel = path.relative_to(package)
        if rel.parts[0] in ('shells', 'harnesses'):
            continue
        text = path.read_text(encoding='utf-8')
        hits.extend(f'{rel.as_posix()}: {key}' for key in _HARNESS_KEYS if key in text)
    return hits


def test_the_scan_finds_a_harness_key_and_skips_shells():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / 'shells' / 'x').mkdir(parents=True)
        (base / 'shells' / 'x' / 'hook.py').write_text(f"K = '{_HARNESS_KEYS[1]}'\n", 'utf-8')
        (base / 'core.py').write_text(f'# reads {_HARNESS_KEYS[5]}\n', 'utf-8')
        assert _harness_shape_hits(base) == [f'core.py: {_HARNESS_KEYS[5]}']


def test_the_core_names_no_harness_payload_key():
    assert (PACKAGE / 'event.py').is_file()
    assert _harness_shape_hits(PACKAGE) == []


if __name__ == '__main__':
    run_module(globals(), 'kit judge')

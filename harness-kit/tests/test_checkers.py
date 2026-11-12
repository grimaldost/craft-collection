#!/usr/bin/env python3
"""Checks of the `check` matcher: loading a checker, calling it, its budget and its result.

Contract under test:
- a checker file defines `check(act, observation)` and returns a dict whose
  `result` is `match`, `no-match` or `cannot-tell`, with an optional string
  `detail`; anything else, an exception (`SystemExit` included), a file that
  does not execute or defines no callable `check`, or a call still running when
  its wait ends reads `cannot-tell`;
- the judge executes the bytes the policy load hashed, once per process, under
  a module name no package module can have, with `__file__` set and the module
  in `sys.modules`, and writes no bytecode;
- one judgement spends at most 500 ms waiting on checkers; a checker is not
  called once less than 50 ms of that is left;
- `check` is evaluated after `kinds` and the other matchers, only when none of
  them gave no-match; its result enters the rule table unchanged;
- a deny whose checker returned a `detail` carries the detail, one space and
  the rule's reason (ASCII, cut to 200 characters);
- `try_load` tests that a checker executes and defines a callable `check`
  within its `budget_ms`, with descriptors 1 and 2 at the null device for the
  load only.

Stdlib-runnable: `python test_checkers.py`.
"""

from __future__ import annotations

import copy
import hashlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import checkers
from harness_kit.policy import load_policy_text
from harness_kit.verdict import VERDICT_KEYS, judge
from kit_fixtures import SRC, event, run_module, write_event

MATCH = 'def check(act, observation):\n    return {"result": "match"}\n'


class Folder:
    """A scratch folder that holds checker files and builds version 2 policies over them."""

    def __init__(self, base: str) -> None:
        self.base = Path(base)
        self.n = 0

    def checker(self, body: str, budget_ms: int | None = None) -> str:
        """Write one checker file; return its [[checker]] table, id `c<n>`."""
        self.n += 1
        path = self.base / f'check_{self.n}.py'
        data = body.encode('utf-8')
        path.write_bytes(data)
        sha = hashlib.sha256(data).hexdigest()
        budget = '' if budget_ms is None else f'budget_ms = {budget_ms}\n'
        return (
            f'[[checker]]\nid = "c{self.n}"\nfile = "{path.as_posix()}"\n'
            f'sha256 = "{sha}"\n{budget}\n'
        )

    def marker(self, name: str) -> Path:
        return self.base / name


def _rule(check: str | None, governed: bool = False, extra: str = '', **over: str) -> str:
    lines = {
        'id': '"r"',
        'effect': '"deny"',
        'governed': 'true' if governed else 'false',
        'kinds': '["shell"]',
    }
    if check:
        lines['check'] = f'"{check}"'
    lines['reason'] = '"use uv"'
    lines.update(over)
    return '[[rule]]\n' + ''.join(f'{k} = {v}\n' for k, v in lines.items()) + extra + '\n'


def _policy(*parts: str):
    return load_policy_text('version = 2\n\n' + ''.join(parts))


def _verdict(policy, ev=None) -> dict:
    v = judge(event() if ev is None else ev, policy)
    assert list(v) == list(VERDICT_KEYS), v
    return v


def _returns(value: str) -> str:
    return f'def check(act, observation):\n    return {value}\n'


def _marking(marker: Path, value: str = '{"result": "match"}') -> str:
    return (
        'def check(act, observation):\n'
        f'    open({str(marker)!r}, "a").close()\n'
        f'    return {value}\n'
    )


def test_each_result_in_a_rule_alone():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        cases = {
            '{"result": "match"}': ('deny', 'r'),
            '{"result": "no-match"}': ('allow', None),
            '{"result": "cannot-tell"}': ('allow', None),
        }
        for value, expected in cases.items():
            table = f.checker(_returns(value))
            v = _verdict(_policy(table, _rule(f'c{f.n}')))
            assert (v['verdict'], v['rule']) == expected, (value, v)
        table = f.checker(_returns('{"result": "cannot-tell"}'))
        v = _verdict(_policy(table, _rule(f'c{f.n}', governed=True)))
        assert (v['verdict'], v['governed'], v['rule']) == ('unknown', True, 'r'), v


def test_a_match_denies_with_the_rule_governance():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        table = f.checker(MATCH)
        v = _verdict(_policy(table, _rule('c1')))
        assert (v['verdict'], v['effect'], v['governed'], v['reason']) == (
            'deny',
            'deny',
            False,
            'use uv',
        ), v


def test_beside_a_command_regex_the_table_is_unchanged():
    match, unavailable = (
        event(**{'act.command': 'pip install x'}),
        event(**{'act.command': None, 'observation.command': 'unavailable'}),
    )
    rows = [
        # (regex event, checker result, expected verdict of a governed deny rule)
        (match, 'match', 'deny'),
        (match, 'no-match', 'allow'),
        (match, 'cannot-tell', 'unknown'),
        (unavailable, 'match', 'unknown'),
        (unavailable, 'no-match', 'allow'),
        (unavailable, 'cannot-tell', 'unknown'),
    ]
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        for ev, result, expected in rows:
            table = f.checker(_returns(f'{{"result": "{result}"}}'))
            rule = _rule(f'c{f.n}', governed=True, command_regex='"pip"')
            v = _verdict(_policy(table, rule), ev)
            assert v['verdict'] == expected, (ev['act']['command'], result, v)


def test_the_checker_is_not_called_when_another_matcher_gave_no_match():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        marker = f.marker('called.marker')
        table = f.checker(_marking(marker))
        policy = _policy(table, _rule('c1', command_regex='"pip"'))
        v = _verdict(policy, event(**{'act.command': 'echo hi'}))
        assert v['verdict'] == 'allow', v
        v = _verdict(policy, write_event(['/w/a.txt']))
        assert v['verdict'] == 'allow', v
        assert not marker.exists()
        v = _verdict(policy, event(**{'act.command': 'pip install x'}))
        assert v['verdict'] == 'deny' and marker.exists(), v


def test_each_bad_checker_reads_cannot_tell():
    bodies = {
        'raises': 'def check(act, observation):\n    raise RuntimeError("x")\n',
        'sys.exit': 'import sys\ndef check(act, observation):\n    sys.exit(3)\n',
        'base exception': 'def check(act, observation):\n    raise KeyboardInterrupt\n',
        'non-dict': _returns('"match"'),
        'none': _returns('None'),
        'unknown result': _returns('{"result": "yes"}'),
        'no result': _returns('{"detail": "x"}'),
        'extra key': _returns('{"result": "match", "why": "x"}'),
        'detail not a string': _returns('{"result": "match", "detail": 3}'),
        'dict subclass with extra key': (
            'class D(dict):\n    pass\n'
            'def check(act, observation):\n    return D(result="match", other=1)\n'
        ),
        'no check': 'X = 1\n',
        'check not callable': 'check = 3\n',
        'syntax error': 'def check(act, observation)\n    return {}\n',
        'raises while it loads': 'raise ValueError("load")\n',
        'exits while it loads': 'raise SystemExit(0)\n',
    }
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        for label, body in bodies.items():
            table = f.checker(body)
            v = _verdict(_policy(table, _rule(f'c{f.n}', governed=True)))
            assert (v['verdict'], v['rule']) == ('unknown', 'r'), (label, v)


def test_a_checker_past_its_budget_reads_cannot_tell():
    sleeper = 'import time\ndef check(act, observation):\n    time.sleep(3)\n    return {"result": "match"}\n'
    loader = 'import time\ntime.sleep(3)\n' + MATCH
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        for body in (sleeper, loader):
            table = f.checker(body, budget_ms=100)
            start = time.monotonic()
            v = _verdict(_policy(table, _rule(f'c{f.n}', governed=True)))
            elapsed = time.monotonic() - start
            assert v['verdict'] == 'unknown', v
            assert elapsed < 1.0, elapsed


def test_the_total_budget_leaves_the_third_slow_checker_uncalled():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        parts = []
        markers = []
        for n in range(3):
            marker = f.marker(f'called-{n}.marker')
            markers.append(marker)
            body = (
                'import time\n'
                'def check(act, observation):\n'
                f'    open({str(marker)!r}, "a").close()\n'
                '    time.sleep(2)\n'
                '    return {"result": "match"}\n'
            )
            parts.append(f.checker(body, budget_ms=250))
            parts.append(_rule(f'c{f.n}', id=f'"r{n}"'))
        start = time.monotonic()
        v = _verdict(_policy(*parts))
        elapsed = time.monotonic() - start
        # A third checker called with no wait left would still write its marker
        # a moment after the judgement returns; wait past that before looking.
        time.sleep(0.5)
        assert v['verdict'] == 'allow', v
        assert markers[0].exists() and markers[1].exists()
        assert not markers[2].exists()
        assert 0.45 < elapsed < 1.2, elapsed


def test_a_detail_leads_the_reason_of_a_deny():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        table = f.checker(_returns('{"result": "match", "detail": "Blocked `pip install`."}'))
        v = _verdict(_policy(table, _rule('c1')))
        assert v['reason'] == 'Blocked `pip install`. use uv', v
        table = f.checker(_returns('{"result": "match", "detail": "Blocked."}'))
        v = _verdict(_policy(table, _rule('c2', reason='""')))
        assert v['reason'] == 'Blocked.', v
        table = f.checker(_returns('{"result": "match", "detail": "caf\\u00e9 \\U0001f600"}'))
        v = _verdict(_policy(table, _rule('c3')))
        assert v['reason'] == 'caf\\xe9 \\U0001f600 use uv', v
        table = f.checker(_returns('{"result": "match", "detail": "\\u00e9" * 300}'))
        v = _verdict(_policy(table, _rule('c4')))
        assert v['reason'] == '\\xe9' * 50 + ' use uv', v
        table = f.checker(_returns('{"result": "match", "detail": "d"}'))
        v = _verdict(_policy(table, _rule('c5', effect='"allow"')))
        assert (v['verdict'], v['reason']) == ('allow', 'use uv'), v


def test_the_checker_gets_copies_of_act_and_observation():
    body = (
        'def check(act, observation):\n'
        '    seen = (act["kind"], observation["command"])\n'
        '    act.clear()\n'
        '    observation.clear()\n'
        '    return {"result": "match" if seen == ("shell", "observed") else "no-match"}\n'
    )
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        table = f.checker(body)
        ev = event()
        before = copy.deepcopy(ev)
        v = _verdict(_policy(table, _rule('c1')), ev)
        assert v['verdict'] == 'deny', v
        assert ev == before


def test_the_module_is_loaded_once_under_a_name_no_package_can_have():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        record = f.marker('record.txt')
        body = (
            'import sys\n'
            f'with open({str(record)!r}, "a", encoding="utf-8") as out:\n'
            '    out.write(repr((__name__, __file__, sys.modules.get(__name__) is not None)) + "\\n")\n'
            + MATCH
        )
        table = f.checker(body)
        policy = _policy(table, _rule('c1'))
        for _ in range(2):
            assert _verdict(policy)['verdict'] == 'deny'
        lines = record.read_text(encoding='utf-8').splitlines()
        assert len(lines) == 1, lines
        name, file, entered = eval(lines[0])  # noqa: S307 - our own repr of a tuple
        assert not name.isidentifier() and name not in ('__main__', 'check_1'), name
        assert Path(file) == Path(td) / 'check_1.py', file
        assert entered is True
        assert sys.modules[name].__file__ == file
        assert checkers.module_name(policy.checkers[0]) == name
        assert not any(p.name == '__pycache__' for p in Path(td).rglob('*'))


def test_the_judge_executes_the_bytes_it_hashed():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        table = f.checker(MATCH)
        policy = _policy(table, _rule('c1'))
        (Path(td) / 'check_1.py').write_text(_returns('{"result": "no-match"}'), encoding='utf-8')
        assert _verdict(policy)['verdict'] == 'deny'


def _checker_of(f: Folder, body: str, budget_ms: int | None = None):
    table = f.checker(body, budget_ms)
    return _policy(table).checkers[0]


def test_try_load_accepts_a_sound_checker_and_names_each_fault():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        assert checkers.try_load(_checker_of(f, MATCH)) is None
        faults = {
            'syntax error': 'def check(\n',
            'no check': 'X = 1\n',
            'check not callable': 'check = "x"\n',
            'raises while it loads': 'raise ValueError("load")\n',
            'exits while it loads': 'import sys\nsys.exit(0)\n',
        }
        for label, body in faults.items():
            reason = checkers.try_load(_checker_of(f, body))
            assert isinstance(reason, str) and reason and reason.isascii(), (label, reason)


def test_try_load_waits_no_longer_than_the_budget():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        checker = _checker_of(f, 'import time\ntime.sleep(10)\n' + MATCH, budget_ms=100)
        start = time.monotonic()
        reason = checkers.try_load(checker)
        assert reason and time.monotonic() - start < 1.0, reason


def test_try_load_and_the_judge_share_one_load():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        record = f.marker('loads.txt')
        body = f'open({str(record)!r}, "a").write("x")\n' + MATCH
        table = f.checker(body)
        policy = _policy(table, _rule('c1'))
        assert checkers.try_load(policy.checkers[0]) is None
        assert _verdict(policy)['verdict'] == 'deny'
        assert record.read_text() == 'x'


_QUIET_SCRIPT = """\
import os, subprocess, sys
from harness_kit import checkers
from harness_kit.policy import load_policy_text
policy = load_policy_text(sys.stdin.read())
print('before', flush=True)
reason = checkers.try_load(policy.checkers[0])
print('after', reason, flush=True)
sys.stderr.write('stderr after\\n')
"""

_NOISY_LOAD = """\
import os, subprocess, sys
print('load print')
sys.stderr.write('load stderr\\n')
os.write(1, b'load fd1\\n')
os.write(2, b'load fd2\\n')
sys.__stdout__.write('load dunder\\n')
sys.__stdout__.flush()
subprocess.run([sys.executable, '-c', 'print("load child")'], check=False)
def check(act, observation):
    return {"result": "match"}
"""


def test_try_load_silences_the_load_and_restores_the_streams():
    with tempfile.TemporaryDirectory() as td:
        f = Folder(td)
        table = f.checker(_NOISY_LOAD)
        env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
        env['PYTHONPATH'] = str(SRC)
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, '-c', _QUIET_SCRIPT],
            input='version = 2\n' + table,
            capture_output=True,
            text=True,
            encoding='utf-8',
            env=env,
            timeout=60,
        )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ['before', 'after None'], proc.stdout
    assert proc.stderr.splitlines() == ['stderr after'], proc.stderr


if __name__ == '__main__':
    run_module(globals(), 'checkers')

#!/usr/bin/env python3
"""A rendered home under the real harness: one denied shell call and one allowed call.

For each harness: render a home at a local stub, script two shell calls (the
first matches a denying rule, the second matches nothing), run the harness
headless in a work folder under the base, and read the markers on disk: the
denied call's marker is absent and the rule's reason reaches the next stub
request; the allowed call's marker is present. The harness's exit code is not
read as proof. opencode events need a launched run, so its session gets a run
id minted by `kit state new-run`.

Prints `skip:` unless KIT_CONFORMANCE_BASE, KIT_HARNESS_ARGV_CLAUDE_CODE and
KIT_HARNESS_ARGV_OPENCODE are set; the base must be an existing folder.

Stdlib-runnable: `python test_real_homes.py`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import harnesses
from kit_fixtures import SRC

REQUIRED = ('KIT_CONFORMANCE_BASE', 'KIT_HARNESS_ARGV_CLAUDE_CODE', 'KIT_HARNESS_ARGV_OPENCODE')
REASON = 'KIT-HOME-REASON'
SECRET_NAME = re.compile(r'(^GH_|_KEY$|_TOKEN$|_SECRET$|_PASSWORD$)', re.IGNORECASE)
POLICY = f"""\
version = 1

[launcher]
test_roots = []
forbidden_roots = []

[[rule]]
id = "home-deny"
effect = "deny"
governed = true
kinds = ["shell"]
command_regex = "deny-home\\\\.marker"
reason = "{REASON}"
"""


def _kit_env(extra: dict) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env = {k: v for k, v in env.items() if not SECRET_NAME.search(k)}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    env.update(extra)
    return env


def _kit(*args: str, env: dict) -> str:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, (args, proc.returncode, proc.stderr)
    return proc.stdout


def _start_stub(folder: Path, steps: list, env: dict) -> tuple[subprocess.Popen, int]:
    script = folder / 'script.json'
    script.write_text(json.dumps(steps), encoding='utf-8')
    stub = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        [
            sys.executable,
            '-m',
            'harness_kit',
            'stub',
            '--log',
            str(folder / 'stub.jsonl'),
            '--script',
            str(script),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding='utf-8',
        env=env,
    )
    return stub, json.loads(stub.stdout.readline())['port']


def _log(folder: Path) -> list[dict]:
    path = folder / 'stub.jsonl'
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def run_harness(name: str, base: Path) -> dict:
    driver = harnesses.get(name)
    folder = base / f'{name}-{time.strftime("%H%M%S")}'
    work, tmp = folder / 'work', folder / 'tmp'
    for sub in (work, tmp):
        sub.mkdir(parents=True)
    policy = folder / 'policy.toml'
    policy.write_text(POLICY, encoding='utf-8')
    kit = {'KIT_POLICY': str(policy), 'KIT_STATE_ROOT': str(folder / 'state')}
    kit_env = _kit_env(kit)
    steps = [
        driver.canary_step('echo probe > deny-home.marker'),
        driver.canary_step('echo probe > allow-home.marker'),
        {'text': 'done'},
    ]
    stub, port = _start_stub(folder, steps, kit_env)
    try:
        endpoint = f'http://127.0.0.1:{port}'
        rendered = _kit(
            'home',
            'render',
            '--harness',
            name,
            '--dir',
            str(folder / 'home'),
            '--endpoint',
            endpoint,
            env=kit_env,
        )
        home = json.loads(rendered)
        if name != 'claude-code':
            minted = json.loads(_kit('state', 'new-run', '--harness', name, env=kit_env))
            kit['KIT_RUN_ID'] = minted['run_id']
        session_base = {k: v for k, v in kit_env.items() if k != 'PYTHONPATH'}
        session_base.update(kit, TEMP=str(tmp), TMP=str(tmp), PWD=str(work))
        env = driver.session_env(home, session_base)
        argv = driver.binary_argv(env)
        assert argv, f'{name}: binary missing'
        with open(folder / 'stdout.txt', 'wb') as out, open(folder / 'stderr.txt', 'wb') as err:
            subprocess.run(  # noqa: S603 - argv from the driver, no shell
                argv + driver.canary_argv('Run the scripted tool calls.'),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                env=env,
                cwd=str(work),
                timeout=240,
                check=False,
            )
    finally:
        stub.kill()
        stub.wait()
    later = [r for r in _log(folder) if (r.get('step_index') or 0) >= 1]
    after_first = json.dumps([r.get('body') for r in later])
    return {
        'harness': name,
        'folder': str(folder),
        'deny_marker_absent': not (work / 'deny-home.marker').exists(),
        'allow_marker_present': (work / 'allow-home.marker').exists(),
        'reason_after_tool_call': REASON in after_first,
    }


def main() -> int:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        print(f'skip: real-harness homes need {", ".join(missing)}')
        return 0
    base = Path(os.environ['KIT_CONFORMANCE_BASE'])
    if not base.is_dir():
        print('FAIL: KIT_CONFORMANCE_BASE is not an existing folder')
        return 1
    rows = [run_harness(name, base) for name in ('claude-code', 'opencode')]
    print(json.dumps(rows, indent=2))
    bad = [r for r in rows if not all(v for k, v in r.items() if k not in ('harness', 'folder'))]
    if bad:
        print('FAIL: ' + ', '.join(r['harness'] for r in bad))
        return 1
    print('ok: real harness homes (deny and allow on both harnesses)')
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Checks of the opencode shell (`shells/opencode/index.js`), run under Node with a fake host.

Contract under test:
- the module exports id `harness-kit` and registers one `execute.before` hook;
- the neutral event it sends to the CLI: tool mapping, paths, parent and origin from the session
  lookup in its four outcomes (no parent, a parent, a throw, a lookup that never resolves);
- effect allow returns, effect deny throws the reason;
- each failure class throws a reason that starts `kit could not judge:`;
- a hung CLI settles within 4.5 seconds and its grandchild never writes its late marker (Windows);
- the plugin settles only once the killer has exited (a slow killer is waited for, up to a second);
- the file names no bare kill command, has an error handler on the killer, imports only Node
  built-ins and holds at most 160 non-blank lines.

Stdlib-runnable: `python test_opencode_shell.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHELL_SRC = HERE.parent / 'src' / 'harness_kit' / 'shells' / 'opencode' / 'index.js'
DRIVER = HERE / 'opencode_driver.mjs'
STANDIN = HERE / 'opencode_standin_cli.py'
NODE = shutil.which('node')
IS_WINDOWS = os.name == 'nt'
PREFIX = 'kit could not judge:'


class Scene:
    """A temp folder holding a copy of the shell, its config and the stand-in's record files."""

    def __init__(self, mode: str, config: object = 'default'):
        self.td = tempfile.TemporaryDirectory()
        self.base = Path(self.td.name)
        self.shell_dir = self.base / 'shell'
        self.shell_dir.mkdir()
        shutil.copy(SHELL_SRC, self.shell_dir / 'index.js')
        self.record = self.base / 'record.json'
        self.marker = self.base / 'late-marker.txt'
        if config == 'default':
            argv = [sys.executable, '-I', str(STANDIN), mode, str(self.record), str(self.marker)]
            config = {
                'kit_shell_config': 1,
                'cli_argv': argv,
                'timeout_s': 3,
                'harness_version': '2.2.5',
            }
        if config is not None:
            text = config if isinstance(config, str) else json.dumps(config)
            (self.shell_dir / 'shell_config.json').write_text(text, encoding='utf-8')

    def close(self) -> None:
        self.td.cleanup()

    def start(
        self,
        event: object,
        session: str = 'none',
        env: dict | None = None,
        killer_delay_ms: int = 0,
    ):
        spec = {
            'shell': str(self.shell_dir / 'index.js'),
            'directory': '/w',
            'session': session,
            'event': event,
            'killerDelayMs': killer_delay_ms,
        }
        proc = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [NODE, str(DRIVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            env=env,
        )
        proc.stdin.write(json.dumps(spec))
        proc.stdin.close()
        return proc

    def run(self, event: object, session: str = 'none') -> dict:
        proc = self.start(event, session)
        out, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, f'driver failed: {err}'
        return json.loads(out.strip().splitlines()[-1])

    def sent(self) -> dict:
        return json.loads(self.record.read_text(encoding='utf-8'))


def shell_event(command: str = 'echo hi') -> dict:
    return {
        'tool': 'shell',
        'sessionID': 's1',
        'agent': 'a',
        'messageID': 'm',
        'id': 'c',
        'input': {'command': command},
    }


def judged(event: object, session: str = 'none', mode: str = 'allow') -> tuple[dict, dict]:
    scene = Scene(mode)
    try:
        out = scene.run(event, session)
        sent = scene.sent() if scene.record.exists() else {}
        return out, sent
    finally:
        scene.close()


def sha(event: dict) -> str:
    return hashlib.sha256(json.dumps(event, separators=(',', ':')).encode('utf-8')).hexdigest()


def test_registers_one_execute_before_hook_under_the_shell_id():
    out, _ = judged(shell_event())
    assert out['id'] == 'harness-kit', out
    assert out['hooks'] == ['execute.before'], out


def test_shell_event_without_a_parent_is_exactly_the_neutral_event():
    ev = shell_event('echo hi')
    out, sent = judged(ev)
    assert out['threw'] is False, out
    assert out['gets'] == [{'sessionID': 's1'}], out
    expected = {
        'kit_event': 1,
        'run_id': None,
        'harness': {'name': 'opencode', 'version': '2.2.5'},
        'session': {'id': 's1', 'parent_id': None, 'root_id': 's1'},
        'origin': 'unknown',
        'observation': {
            'session': 'observed',
            'parent': 'observed',
            'root': 'observed',
            'origin': 'unavailable',
            'command': 'observed',
            'paths': 'not_applicable',
        },
        'act': {
            'kind': 'shell',
            'command': 'echo hi',
            'argv': None,
            'paths': [],
            'cwd': '/w',
            'payload_sha256': sha(ev),
        },
    }
    assert sent == expected, sent


def test_a_parent_makes_the_origin_child_and_leaves_the_root_unavailable():
    _, sent = judged(shell_event(), session='parent')
    assert sent['session'] == {'id': 's1', 'parent_id': 'parent-1', 'root_id': None}, sent
    assert sent['origin'] == 'child', sent
    obs = sent['observation']
    assert (obs['parent'], obs['root'], obs['origin']) == ('observed', 'unavailable', 'observed')


def _assert_lookup_unavailable(sent):
    assert sent['session'] == {'id': 's1', 'parent_id': None, 'root_id': None}, sent
    assert sent['origin'] == 'unknown', sent
    obs = sent['observation']
    assert (obs['parent'], obs['root'], obs['origin']) == ('unavailable',) * 3, obs
    assert obs['session'] == 'observed', obs


def test_a_lookup_that_throws_still_reaches_the_cli_with_three_fields_unavailable():
    out, sent = judged(shell_event(), session='throw')
    assert out['threw'] is False, out
    _assert_lookup_unavailable(sent)


def test_a_lookup_that_never_resolves_still_reaches_the_cli_within_the_deadline():
    out, sent = judged(shell_event(), session='hang')
    assert out['threw'] is False, out
    assert 900 <= out['elapsed_ms'] < 4500, out
    _assert_lookup_unavailable(sent)


def test_write_and_edit_are_file_writes_with_the_path_resolved_against_the_directory():
    for tool in ('write', 'edit'):
        ev = {'tool': tool, 'sessionID': 's1', 'input': {'path': 'sub/a.txt'}}
        _, sent = judged(ev)
        act = sent['act']
        assert act['kind'] == 'file_write' and act['command'] is None, act
        assert act['paths'] == [str(Path('/w').resolve() / 'sub' / 'a.txt')], act
        assert sent['observation']['command'] == 'not_applicable', sent
        assert sent['observation']['paths'] == 'observed', sent


def test_patch_is_a_file_write_with_no_paths_and_unavailable_observation():
    ev = {'tool': 'patch', 'sessionID': 's1', 'input': {'patchText': 'x'}}
    _, sent = judged(ev)
    assert sent['act']['kind'] == 'file_write' and sent['act']['paths'] == [], sent
    assert sent['observation']['paths'] == 'unavailable', sent
    assert sent['observation']['command'] == 'not_applicable', sent


def test_any_other_tool_is_other_with_both_observations_not_applicable():
    ev = {'tool': 'grep', 'sessionID': 's1', 'input': {'pattern': 'x'}}
    _, sent = judged(ev)
    assert sent['act']['kind'] == 'other' and sent['act']['command'] is None, sent
    assert sent['act']['paths'] == [], sent
    obs = sent['observation']
    assert (obs['command'], obs['paths']) == ('not_applicable', 'not_applicable'), obs


def test_allow_returns():
    out, _ = judged(shell_event(), mode='allow')
    assert out['threw'] is False, out


def test_deny_throws_the_reason_as_is():
    out, _ = judged(shell_event(), mode='deny')
    assert out['threw'] is True and out['message'] == 'blocked by test rule', out


def test_a_non_ascii_command_reaches_the_cli_intact():
    _, sent = judged(shell_event('echo caf\u00e9 \u4e2d'))
    assert sent['act']['command'] == 'echo caf\u00e9 \u4e2d', sent


def _assert_could_not_judge(out):
    assert out['threw'] is True, out
    assert out['message'].startswith(PREFIX), out


def test_each_cli_failure_class_throws_could_not_judge():
    for mode in ('exit1', 'empty', 'garbage', 'not_a_verdict'):
        out, _ = judged(shell_event(), mode=mode)
        _assert_could_not_judge(out)


def _scene_with(config) -> dict:
    scene = Scene('allow', config=config)
    try:
        return scene.run(shell_event())
    finally:
        scene.close()


def test_a_cli_that_cannot_start_throws_could_not_judge():
    missing = str(Path(tempfile.gettempdir()) / 'no-such-binary-for-kit')
    config = {
        'kit_shell_config': 1,
        'cli_argv': [missing, 'judge'],
        'timeout_s': 3,
        'harness_version': '2.2.5',
    }
    _assert_could_not_judge(_scene_with(config))


def test_a_missing_or_malformed_config_throws_could_not_judge():
    good = {'kit_shell_config': 1, 'cli_argv': ['x'], 'timeout_s': 3, 'harness_version': '2.2.5'}
    bad_configs = [
        None,
        '{not json',
        '[]',
        json.dumps({**good, 'cli_argv': []}),
        json.dumps({**good, 'kit_shell_config': 2}),
        json.dumps({**good, 'timeout_s': 'soon'}),
    ]
    for config in bad_configs:
        _assert_could_not_judge(_scene_with(config))


def test_an_unreadable_payload_throws_could_not_judge():
    for bad in (None, 'text', 7):
        out, _ = judged(bad)
        _assert_could_not_judge(out)


def _without_system32(env: dict) -> dict:
    system32 = os.path.join(env.get('SystemRoot', 'C:\\Windows'), 'System32').lower()
    kept = [
        p
        for p in env.get('PATH', '').split(os.pathsep)
        if not p.lower().rstrip('\\').startswith(system32)
    ]
    return {**env, 'PATH': os.pathsep.join(kept)}


def test_a_hung_cli_settles_within_4_5_seconds_and_its_grandchild_never_writes():
    if not IS_WINDOWS:
        return  # the POSIX kill is unmeasured in this slice and has no check here
    runs = []
    for env in (None, _without_system32(dict(os.environ))):
        scene = Scene('hang')
        runs.append((scene, scene.start(shell_event(), env=env), time.monotonic()))
    for _scene, proc, t0 in runs:
        out, _ = proc.communicate(timeout=30)
        wall = time.monotonic() - t0
        result = json.loads(out.strip().splitlines()[-1])
        _assert_could_not_judge(result)
        assert result['elapsed_ms'] < 4500, result
        assert wall < 6.0, wall
    time.sleep(7)
    for scene, _, _ in runs:
        try:
            assert not scene.marker.exists(), 'the grandchild wrote its late marker'
        finally:
            scene.close()


def test_a_slow_killer_is_waited_for_before_the_plugin_settles():
    """A host that tears its tree down when the plugin settles must not cut the killer short."""
    if not IS_WINDOWS:
        return  # the POSIX kill is unmeasured in this slice and has no check here
    scene = Scene('hang')
    try:
        proc = scene.start(shell_event(), killer_delay_ms=400)
        text, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, f'driver failed: {err}'
        out = json.loads(text.strip().splitlines()[-1])
        _assert_could_not_judge(out)
        assert out['killer_done'] is True, 'the plugin settled before the killer had exited'
        # the 3 s deadline, then the killer's 0.4 s delay and its run
        assert 3400 <= out['elapsed_ms'] < 4500, out
        time.sleep(7)
        assert not scene.marker.exists(), 'the grandchild wrote its late marker'
    finally:
        scene.close()


def _source() -> str:
    return SHELL_SRC.read_text(encoding='utf-8')


def test_source_has_no_bare_kill_command_and_an_error_handler_on_the_killer():
    src = _source()
    assert not re.search(r'["\']taskkill', src), 'a bare kill command is named'
    assert not re.search(r'(?<![\\/])taskkill', src), 'a kill command is named without a path'
    assert '.on("error"' in src, 'the killer has no error handler'


def test_source_imports_only_node_built_ins_and_stays_within_160_lines():
    src = _source()
    specs = re.findall(r'(?:from|import)\s*\(?\s*["\']([^"\']+)["\']', src)
    assert specs and all(s.startswith('node:') for s in specs), specs
    assert 'harness_kit' not in src
    assert 'shell: true' not in src
    lines = [ln for ln in src.splitlines() if ln.strip()]
    assert len(lines) <= 160, len(lines)


def test_source_is_ascii():
    _source().encode('ascii')


if __name__ == '__main__':
    if NODE is None:
        print('skip: node is not installed')
        sys.exit(0)
    names = sorted(n for n, f in dict(globals()).items() if n.startswith('test_') and callable(f))
    for name in names:
        globals()[name]()
    print(f'ok: opencode shell ({len(names)} checks)')

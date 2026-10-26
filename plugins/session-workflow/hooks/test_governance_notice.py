"""Tests for governance_notice.py: a change to the governed CLAUDE.md is announced once.

The owner's governance file is edited by one supervising session while other
sessions keep running, many of them woken only by task notifications and
subagent hand-backs. The notice records a baseline hash of the governed
`CLAUDE.md` at SessionStart (only when the session has none) and, on every
UserPromptSubmit, owner-typed or synthetic, compares it; a change is announced
in one line of additionalContext and then becomes the new baseline.

Every case drives the real hook contract: a subprocess fed a JSON payload on
stdin, with a child whose stdout is cp1252 and has no UTF-8 mode, and the
governed home pointed at a temporary directory through
`$SESSION_WORKFLOW_GOVERNED_HOME`, so nothing here reads or changes the real one.

Stdlib-runnable: `python plugins/session-workflow/hooks/test_governance_notice.py` prints `ok:`.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import governance_notice as notice

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'governance_notice.py'
HOOKS_JSON = HERE / 'hooks.json'

SESSION = 'test-session-gov-0001'
OTHER_SESSION = 'test-session-gov-0002'
TASK_NOTIFICATION = (
    '<task-notification>\n<task-id>b1</task-id>\n<status>completed</status>\n'
    '<summary>Background command completed (exit code 0)</summary>\n</task-notification>'
)
HAND_BACK = (
    'Another Claude session sent a message:\n<agent-message from="a1">\n'
    '[Subagent hand-back] The text below is the final report of a subagent.\n</agent-message>'
)
OWNER = 'pode seguir'
DROP = (
    'PYTHONUTF8',
    'CLAUDE_PLUGIN_DATA',
    'CLAUDE_CONFIG_DIR',
    'SESSION_WORKFLOW_GOVERNED_HOME',
    'SESSION_WORKFLOW_GOVERNANCE_NOTICE',
    'SESSION_WORKFLOW_GOVERNANCE_NOTICE_DIR',
)


class Rig:
    """A temporary governed home and state directory, and the hook run against them."""

    def __init__(self, root: Path, home_name: str = 'governed', gate: str | None = None):
        self.home = root / home_name
        self.home.mkdir(parents=True)
        self.state = root / 'plugin-data'
        self.claude_md = self.home / 'CLAUDE.md'
        self.env = {k: v for k, v in os.environ.items() if k not in DROP}
        self.env['PYTHONIOENCODING'] = 'cp1252'
        self.env['SESSION_WORKFLOW_GOVERNED_HOME'] = str(self.home)
        self.env['CLAUDE_PLUGIN_DATA'] = str(self.state)
        if gate is not None:
            self.env['SESSION_WORKFLOW_GOVERNANCE_NOTICE'] = gate

    def write(self, text: str) -> None:
        self.claude_md.write_text(text, encoding='utf-8')

    def run(self, flag: str | None, payload, script: Path = SCRIPT) -> subprocess.CompletedProcess:
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode('utf-8')
        argv = [sys.executable, str(script)] + ([flag] if flag else [])
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            argv,
            input=data,
            capture_output=True,
            env=self.env,
            timeout=60,
        )
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        assert proc.stderr == b'', proc.stderr
        return proc

    def start(self, source: str = 'startup', session: str = SESSION) -> subprocess.CompletedProcess:
        payload = {
            'session_id': session,
            'hook_event_name': 'SessionStart',
            'source': source,
            'cwd': str(self.home.parent),
        }
        return self.run('--session-start', payload)

    def prompt(self, text: str, session: str = SESSION) -> subprocess.CompletedProcess:
        payload = {
            'session_id': session,
            'hook_event_name': 'UserPromptSubmit',
            'prompt': text,
            'cwd': str(self.home.parent),
        }
        return self.run('--prompt-submit', payload)


@contextlib.contextmanager
def _rig(**kwargs):
    with tempfile.TemporaryDirectory() as tmp:
        yield Rig(Path(tmp), **kwargs)


def _context(proc: subprocess.CompletedProcess) -> str:
    assert proc.stdout, 'expected a notice, got no output'
    out = json.loads(proc.stdout.decode('utf-8'))
    spec = out['hookSpecificOutput']
    assert spec['hookEventName'] == 'UserPromptSubmit', spec
    assert 'decision' not in out, 'a notice travels as additionalContext, never as a block'
    return spec['additionalContext']


# ------------------------------------------------------------- acceptance (spec section 6)


def test_an_unchanged_file_prints_nothing():
    with _rig() as rig:
        rig.write('# rules v1\n')
        assert rig.start().stdout == b''
        assert rig.prompt(OWNER).stdout == b''
        assert rig.prompt(TASK_NOTIFICATION).stdout == b''


def test_a_change_is_announced_once_on_a_task_notification():
    with _rig() as rig:
        rig.write('# rules v1\n')
        rig.start()
        assert rig.prompt(OWNER).stdout == b''
        rig.write('# rules v2: one more rule\n')
        text = _context(rig.prompt(TASK_NOTIFICATION))
        assert str(rig.claude_md) in text, text
        assert 're-read it before the next act' in text, text
        assert '\n' not in text, 'the notice is one line'
        assert rig.prompt(OWNER).stdout == b'', 'each change is announced once'
        assert rig.prompt(HAND_BACK).stdout == b''


def test_the_notice_names_the_time_the_file_changed():
    with _rig() as rig:
        rig.write('# rules v1\n')
        rig.start()
        rig.write('# rules v2\n')
        stamp = 1_790_000_000  # a fixed modification time, 2026-09-21 UTC
        os.utime(rig.claude_md, (stamp, stamp))
        text = _context(rig.prompt(OWNER))
        assert notice.format_time(stamp) in text, (notice.format_time(stamp), text)


def test_an_owner_typed_prompt_is_also_told():
    with _rig() as rig:
        rig.write('# rules v1\n')
        rig.start()
        rig.write('# rules v2\n')
        assert 'CLAUDE.md' in _context(rig.prompt(OWNER))


def test_a_second_session_start_does_not_absorb_a_change():
    with _rig() as rig:
        rig.write('# rules v1\n')
        rig.start('startup')
        rig.write('# rules v2\n')
        assert rig.start('compact').stdout == b'', 'SessionStart only records a first baseline'
        assert 'CLAUDE.md' in _context(rig.prompt(TASK_NOTIFICATION))
        assert rig.prompt(TASK_NOTIFICATION).stdout == b''


def test_hooks_json_wires_both_entries():
    manifest = json.loads(HOOKS_JSON.read_text(encoding='utf-8'))
    prefix = [
        'run',
        '--no-project',
        '--',
        'python',
        '${CLAUDE_PLUGIN_ROOT}/hooks/governance_notice.py',
    ]
    wired = {}
    for event, groups in manifest['hooks'].items():
        for group in groups:
            for hook in group['hooks']:
                if hook.get('type') == 'command' and hook['args'][: len(prefix)] == prefix:
                    wired.setdefault(event, []).append(
                        (group.get('matcher'), hook['command'], hook['args'][len(prefix) :])
                    )
    assert wired == {
        'SessionStart': [('startup|resume|clear|compact', 'uv', ['--session-start'])],
        'UserPromptSubmit': [(None, 'uv', ['--prompt-submit'])],
    }, wired


# ------------------------------------------------------------------- the hook contract


def test_a_malformed_payload_exits_zero_with_no_output():
    with _rig() as rig:
        rig.write('# rules v1\n')
        rig.start()
        rig.write('# rules v2\n')  # a pending change: only a readable payload may announce it
        for flag in ('--session-start', '--prompt-submit', None):
            for payload in (b'{not json', b'[1, 2]', b'\xff\xfe'):
                assert rig.run(flag, payload).stdout == b''


def test_the_off_switch_prints_and_writes_nothing():
    with _rig(gate='0') as rig:
        rig.write('# rules v1\n')
        rig.start()
        rig.write('# rules v2\n')
        assert rig.prompt(OWNER).stdout == b''
        assert not rig.state.exists(), 'off means no state is written'


def test_any_other_switch_value_keeps_it_on():
    with _rig(gate='1') as rig:
        rig.write('# rules v1\n')
        rig.start()
        rig.write('# rules v2\n')
        assert 'CLAUDE.md' in _context(rig.prompt(OWNER))


def test_a_non_ascii_path_arrives_in_utf8_on_a_cp1252_console():
    with _rig(home_name='governança → home') as rig:
        rig.write('# rules v1\n')
        rig.start()
        rig.write('# rules v2\n')
        proc = rig.prompt(OWNER)
        assert 'governança → home'.encode() in proc.stdout, proc.stdout
        assert str(rig.claude_md) in _context(proc)


def test_the_event_name_selects_the_arm_when_no_flag_is_given():
    with _rig() as rig:
        rig.write('# rules v1\n')
        base = {'session_id': SESSION, 'cwd': str(rig.home.parent)}
        assert rig.run(None, {**base, 'hook_event_name': 'SessionStart'}).stdout == b''
        rig.write('# rules v2\n')
        proc = rig.run(None, {**base, 'hook_event_name': 'UserPromptSubmit', 'prompt': OWNER})
        assert 'CLAUDE.md' in _context(proc)


def test_without_a_baseline_the_first_prompt_records_one_silently():
    # A session whose SessionStart hook did not run (the plugin enabled mid-session)
    # has nothing to compare against: the first prompt records, the next change shows.
    with _rig() as rig:
        rig.write('# rules v1\n')
        assert rig.prompt(OWNER).stdout == b''
        rig.write('# rules v2\n')
        assert 'CLAUDE.md' in _context(rig.prompt(OWNER))


def test_a_touch_without_a_content_change_is_not_a_change():
    with _rig() as rig:
        rig.write('# rules v1\n')
        rig.start()
        stamp = 1_790_000_000
        os.utime(rig.claude_md, (stamp, stamp))
        assert rig.prompt(OWNER).stdout == b''


def test_a_created_and_a_removed_file_are_both_changes():
    with _rig() as rig:
        rig.start()  # no CLAUDE.md yet: the baseline records its absence
        assert rig.prompt(OWNER).stdout == b''
        rig.write('# rules v1\n')
        assert str(rig.claude_md) in _context(rig.prompt(OWNER))
        rig.claude_md.unlink()
        text = _context(rig.prompt(OWNER))
        assert str(rig.claude_md) in text and 'removed' in text, text
        assert rig.prompt(OWNER).stdout == b''


def test_each_session_keeps_its_own_baseline():
    with _rig() as rig:
        rig.write('# rules v1\n')
        rig.start(session=SESSION)
        rig.write('# rules v2\n')
        rig.start(session=OTHER_SESSION)  # starts after the change: v2 is its baseline
        assert rig.prompt(OWNER, session=OTHER_SESSION).stdout == b''
        assert 'CLAUDE.md' in _context(rig.prompt(OWNER, session=SESSION))


def test_the_config_dir_is_the_governed_home_without_the_override():
    with _rig() as rig:
        rig.env.pop('SESSION_WORKFLOW_GOVERNED_HOME')
        rig.env['CLAUDE_CONFIG_DIR'] = str(rig.home)
        rig.write('# rules v1\n')
        rig.start()
        rig.write('# rules v2\n')
        assert str(rig.claude_md) in _context(rig.prompt(OWNER))


def test_a_different_governed_home_does_not_share_the_baseline():
    # The baseline is keyed by the file it describes, so pointing a session's
    # governed home elsewhere starts a fresh baseline instead of a false notice.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        first = Rig(root / 'a')
        second = Rig(root / 'b')
        second.env['CLAUDE_PLUGIN_DATA'] = first.env['CLAUDE_PLUGIN_DATA']
        first.write('# rules A\n')
        second.write('# rules B\n')
        first.start()
        assert second.prompt(OWNER).stdout == b''


def test_without_its_helper_module_it_fails_open():
    # A partial install lacking governed_home.py beside the script cannot resolve
    # the governed path, and must not guess one: exit 0, no output.
    with _rig() as rig, tempfile.TemporaryDirectory() as tmp:
        lone = Path(tmp) / 'governance_notice.py'
        lone.write_text(SCRIPT.read_text(encoding='utf-8'), encoding='utf-8')
        rig.write('# rules v1\n')
        payload = {'session_id': SESSION, 'hook_event_name': 'SessionStart'}
        assert rig.run('--session-start', payload, script=lone).stdout == b''
        rig.write('# rules v2\n')
        payload = {'session_id': SESSION, 'hook_event_name': 'UserPromptSubmit', 'prompt': OWNER}
        assert rig.run('--prompt-submit', payload, script=lone).stdout == b''


def test_a_notice_that_fails_to_print_is_given_again():
    # The new hash is recorded only after the notice was written, so a write that
    # fails leaves the change pending for the next prompt.
    with _rig() as rig:
        rig.write('# rules v1\n')
        saved = {k: os.environ.get(k) for k in DROP}
        try:
            for k in DROP:
                os.environ.pop(k, None)
            os.environ['SESSION_WORKFLOW_GOVERNED_HOME'] = str(rig.home)
            os.environ['CLAUDE_PLUGIN_DATA'] = str(rig.state)
            prompt = {'session_id': SESSION, 'prompt': OWNER}
            notice.handle_session_start({'session_id': SESSION})
            rig.write('# rules v2\n')

            def broken(_output: dict) -> None:
                raise OSError('console closed')

            assert notice.handle_prompt_submit(prompt, emit=broken) is None
            delivered: list[dict] = []
            notice.handle_prompt_submit(prompt, emit=delivered.append)
            assert len(delivered) == 1, delivered
            assert notice.handle_prompt_submit(prompt, emit=delivered.append) is None
            assert len(delivered) == 1, 'announced once after the delivery'
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == '__main__':
    test_an_unchanged_file_prints_nothing()
    test_a_change_is_announced_once_on_a_task_notification()
    test_the_notice_names_the_time_the_file_changed()
    test_an_owner_typed_prompt_is_also_told()
    test_a_second_session_start_does_not_absorb_a_change()
    test_hooks_json_wires_both_entries()
    test_a_malformed_payload_exits_zero_with_no_output()
    test_the_off_switch_prints_and_writes_nothing()
    test_any_other_switch_value_keeps_it_on()
    test_a_non_ascii_path_arrives_in_utf8_on_a_cp1252_console()
    test_the_event_name_selects_the_arm_when_no_flag_is_given()
    test_without_a_baseline_the_first_prompt_records_one_silently()
    test_a_touch_without_a_content_change_is_not_a_change()
    test_a_created_and_a_removed_file_are_both_changes()
    test_each_session_keeps_its_own_baseline()
    test_the_config_dir_is_the_governed_home_without_the_override()
    test_a_different_governed_home_does_not_share_the_baseline()
    test_without_its_helper_module_it_fails_open()
    test_a_notice_that_fails_to_print_is_given_again()
    print('ok: governance_notice announces each change to the governed CLAUDE.md once')

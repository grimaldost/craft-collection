"""Tests for series_guard.py: a second `gh pr create` in one repository and session.

The owner's rule is that a series of two or more PR-sized changes goes through
keel's Definition of Ready and runs with convoy's gate as the judge of each
change. The guard turns that rule into a mechanism at the one exact moment it
can see: the second `gh pr create` in a repository within one session. Its
PostToolUse arm records a repository only when the tool result's stdout carries
a pull URL; its PreToolUse arm denies the next create there unless the command
names the series (`KEEL_SERIES=<path>`) or declares it is none
(`KEEL_SERIES=none:<reason>`).

Every case drives the script as the harness does: a subprocess fed a JSON
payload on stdin, with a cp1252 stdout (`PYTHONIOENCODING=cp1252`, no
`PYTHONUTF8`), and the plugin's data directory pointed at a temporary one.
Repositories are fixture directories whose `.git/config` names an `origin`;
the guard reads that file and never runs git.

Stdlib-runnable: `python plugins/session-workflow/hooks/test_series_guard.py` prints `ok:`.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / 'series_guard.py'
HOOKS_JSON = HERE / 'hooks.json'
GATE = 'SESSION_WORKFLOW_SERIES_GUARD'
SESSION = 'series-guard-test-0001'
URL_OR = 'https://github.com/o/r/pull/1'


# ------------------------------------------------------------------ fixtures


class Box:
    """A temporary world: a plugin data directory, a home, and repositories."""

    def __init__(self, root: Path):
        self.root = root
        self.data = root / 'plugin-data'
        self.home = root / 'home'
        self.data.mkdir()
        self.home.mkdir()

    def repo(self, name: str, origin: str | None) -> Path:
        path = self.root / name
        (path / '.git').mkdir(parents=True)
        config = '[core]\n\trepositoryformatversion = 0\n'
        if origin is not None:
            config += f'[remote "origin"]\n\turl = {origin}\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n'
        (path / '.git' / 'config').write_text(config, encoding='utf-8')
        return path

    def worktree(self, main: Path, name: str) -> Path:
        """A linked worktree: `.git` is a file naming a gitdir whose commondir is the main one."""
        gitdir = main / '.git' / 'worktrees' / name
        gitdir.mkdir(parents=True)
        (gitdir / 'commondir').write_text('../..\n', encoding='utf-8')
        path = self.root / name
        path.mkdir()
        (path / '.git').write_text(f'gitdir: {gitdir.as_posix()}\n', encoding='utf-8')
        return path

    def env(self, mode: str | None = None) -> dict:
        env = {k: v for k, v in os.environ.items() if k not in (GATE, 'PYTHONUTF8')}
        env.pop('KEEL_SERIES', None)
        env['PYTHONIOENCODING'] = 'cp1252'
        env['CLAUDE_PLUGIN_DATA'] = str(self.data)
        env['HOME'] = str(self.home)
        env['USERPROFILE'] = str(self.home)
        if mode is not None:
            env[GATE] = mode
        return env

    def run(self, flag: str, payload: object, mode: str | None = None, raw: bytes | None = None):
        data = raw if raw is not None else json.dumps(payload).encode('utf-8')
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(SCRIPT), flag],
            input=data,
            capture_output=True,
            env=self.env(mode),
            timeout=60,
        )
        return proc

    def pre(self, command: str, cwd: Path, tool: str = 'Bash', session: str = SESSION, mode=None):
        payload = {
            'session_id': session,
            'hook_event_name': 'PreToolUse',
            'cwd': str(cwd),
            'tool_name': tool,
            'tool_input': {'command': command},
        }
        return self.run('--pre-tool-use', payload, mode)

    def post(
        self,
        command: str,
        cwd: Path,
        response: object,
        tool: str = 'Bash',
        session: str = SESSION,
        mode=None,
    ):
        payload = {
            'session_id': session,
            'hook_event_name': 'PostToolUse',
            'cwd': str(cwd),
            'tool_name': tool,
            'tool_input': {'command': command},
            'tool_response': response,
        }
        return self.run('--post-tool-use', payload, mode)

    def created(self, command: str, cwd: Path, url: str = URL_OR, **kw):
        """A successful create: the transcript's toolUseResult shape, the URL on stdout."""
        return self.post(command, cwd, ok_response(url), **kw)

    def log(self) -> list[dict]:
        path = self.data / 'series-guard' / 'log.ndjson'
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def ok_response(stdout: str) -> dict:
    return {
        'stdout': stdout,
        'stderr': '',
        'interrupted': False,
        'isImage': False,
        'noOutputExpected': False,
    }


@contextlib.contextmanager
def box():
    with tempfile.TemporaryDirectory() as tmp:
        yield Box(Path(tmp))


def decision(proc) -> str:
    """'deny' when the hook printed a PreToolUse deny, 'allow' for exit 0 and no output."""
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    out = proc.stdout.decode('utf-8')
    if not out.strip():
        return 'allow'
    data = json.loads(out)
    spec = data['hookSpecificOutput']
    assert spec['hookEventName'] == 'PreToolUse', spec
    return spec['permissionDecision']


def reason(proc) -> str:
    return json.loads(proc.stdout.decode('utf-8'))['hookSpecificOutput']['permissionDecisionReason']


def msys(path: Path) -> str:
    """The Git Bash spelling of a Windows path: C:\\x\\y -> /c/x/y."""
    text = path.as_posix()
    if len(text) > 1 and text[1] == ':':
        return '/' + text[0].lower() + text[2:]
    return text


# ------------------------------------------------------------- the main rule


def test_first_create_in_a_session_is_allowed():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        proc = b.pre('gh pr create -R o/r --title t --body b', cwd)
        assert decision(proc) == 'allow'
        assert proc.stdout == b''


def test_second_create_in_the_same_repo_is_denied():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        cmd = 'gh pr create -R o/r --title t --body b'
        assert decision(b.pre(cmd, cwd)) == 'allow'
        b.created(cmd, cwd)
        proc = b.pre(cmd, cwd)
        assert decision(proc) == 'deny'
        text = reason(proc)
        assert 'Definition of Ready' in text and 'convoy' in text, text
        assert 'KEEL_SERIES=' in text and 'none:' in text, text
        assert '$env:KEEL_SERIES' in text, text
        assert 'o/r' in text, text
        assert any(e.get('decision') == 'deny' and e.get('repo') == 'o/r' for e in b.log())


def test_second_create_without_flag_is_keyed_from_the_ssh_origin():
    with box() as b:
        cwd = b.repo('or', 'git@github.com:O/R.git')
        b.created('gh pr create -R o/r', cwd)
        assert decision(b.pre('gh pr create --fill', cwd)) == 'deny'


def test_origin_is_read_through_a_worktree_common_dir():
    with box() as b:
        main = b.repo('or', 'git@github.com:O/R.git')
        wt = b.worktree(main, 'or-wt')
        b.created('gh pr create -R O/R', main)
        assert decision(b.pre('gh pr create --fill', wt)) == 'deny'


def test_repo_flag_forms_normalize_to_one_key():
    with box() as b:
        cwd = b.repo('elsewhere', 'https://github.com/x/y.git')
        b.created('gh pr create --repo=O/R', cwd)
        assert decision(b.pre('gh pr create -R https://github.com/O/R.git', cwd)) == 'deny'
        assert decision(b.pre('gh pr create --repo "o/r"', cwd)) == 'deny'
        assert decision(b.pre('gh pr create -R github.com/o/r', cwd)) == 'deny'


def test_a_failed_first_attempt_is_not_recorded_and_its_retry_is_allowed():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        cmd = 'gh pr create -R o/r --title t'
        failure = "Error: Exit code 1\npull request create failed: GraphQL: Head sha can't be blank"
        b.post(cmd, cwd, failure)
        b.post(cmd, cwd, ok_response('pull request create failed: no commits'))
        assert decision(b.pre(cmd, cwd)) == 'allow'


def test_a_background_result_is_not_recorded():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        cmd = 'git push -u origin x && gh pr create -R o/r --fill'
        response = {
            'stdout': '',
            'stderr': '',
            'interrupted': False,
            'isImage': False,
            'noOutputExpected': False,
            'backgroundTaskId': 'biym2mib7',
        }
        b.post(cmd, cwd, response)
        assert decision(b.pre(cmd, cwd)) == 'allow'
        # A backgrounded run has not finished, whatever it printed before it moved.
        b.post(cmd, cwd, {**response, 'stdout': URL_OR})
        assert decision(b.pre(cmd, cwd)) == 'allow'


def test_a_pull_url_from_another_command_is_not_recorded():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        cmd = 'echo "gh pr create done" && gh pr view 1 --json url -q .url'
        b.post(cmd, cwd, ok_response(URL_OR))
        assert decision(b.pre('gh pr create --fill', cwd)) == 'allow'


def test_the_record_is_keyed_from_the_url_not_the_payload_cwd():
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('or', 'https://github.com/o/r.git')
        b.created(f'cd {target.as_posix()} && gh pr create --fill', other)
        assert decision(b.pre('gh pr create --fill', target)) == 'deny'
        assert decision(b.pre('gh pr create --fill', other)) == 'allow'


def test_a_first_pr_in_another_repository_is_allowed():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        assert decision(b.pre('gh pr create -R o/other', cwd)) == 'allow'


def test_another_session_counts_on_its_own():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        assert decision(b.pre('gh pr create -R o/r', cwd, session='another-session')) == 'allow'


# ------------------------------------------------------------- KEEL_SERIES


def test_keel_series_naming_an_existing_file_allows_and_logs_bash_form():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        series = b.root / 'series.toml'
        series.write_text('[series]\n', encoding='utf-8')
        b.created('gh pr create -R o/r', cwd)
        proc = b.pre(f'KEEL_SERIES={series.as_posix()} gh pr create -R o/r --fill', cwd)
        assert decision(proc) == 'allow'
        assert any(
            e.get('decision') == 'allow' and e.get('keel_series') == series.as_posix()
            for e in b.log()
        ), b.log()


def test_keel_series_powershell_form_allows_and_logs():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        spec = b.root / 'spec.md'
        spec.write_text('# spec\n', encoding='utf-8')
        b.created('gh pr create -R o/r', cwd, tool='PowerShell')
        cmd = f"$env:KEEL_SERIES='{spec}'; gh pr create -R o/r --fill"
        proc = b.pre(cmd, cwd, tool='PowerShell')
        assert decision(proc) == 'allow'
        assert any(e.get('keel_series') == str(spec) for e in b.log()), b.log()


def test_keel_series_naming_a_missing_file_is_denied():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        missing = b.root / 'n\u00e3o-existe' / 'series.toml'
        proc = b.pre(f'KEEL_SERIES="{missing.as_posix()}" gh pr create -R o/r', cwd)
        assert decision(proc) == 'deny'
        assert proc.stdout.decode('ascii'), 'the deny payload is ASCII on a cp1252 stdout'
        assert 'n\u00e3o-existe' in reason(proc), reason(proc)


def test_keel_series_none_with_a_reason_allows_and_logs():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        assert decision(b.pre('KEEL_SERIES=none:hotfix gh pr create -R o/r', cwd)) == 'allow'
        assert any(
            e.get('decision') == 'allow' and e.get('keel_series') == 'none:hotfix' for e in b.log()
        ), b.log()


def test_keel_series_none_without_a_reason_is_denied():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        assert decision(b.pre('KEEL_SERIES=none: gh pr create -R o/r', cwd)) == 'deny'


def test_keel_series_relative_path_resolves_against_the_payload_cwd():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        (cwd / 'docs').mkdir()
        (cwd / 'docs' / 'series.toml').write_text('[series]\n', encoding='utf-8')
        b.created('gh pr create -R o/r', cwd)
        cmd = 'KEEL_SERIES=docs/series.toml gh pr create -R o/r'
        assert decision(b.pre(cmd, cwd)) == 'allow'


def test_keel_series_relative_path_resolves_against_the_cd_directory():
    # R6-3: the base of a relative KEEL_SERIES path is the working directory the
    # guard derives (here from the opening `cd`), not the payload cwd.
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('or', 'https://github.com/o/r.git')
        (target / 'plan').mkdir()
        (target / 'plan' / 'series.toml').write_text('[series]\n', encoding='utf-8')
        b.created('gh pr create -R o/r', target)
        cmd = f'cd {target.as_posix()} && KEEL_SERIES=plan/series.toml gh pr create --fill'
        assert decision(b.pre(cmd, other)) == 'allow'
        bad = f'cd {target.as_posix()} && KEEL_SERIES=plan/missing.toml gh pr create --fill'
        assert decision(b.pre(bad, other)) == 'deny'


def test_keel_series_powershell_backslash_path_resolves_on_any_host():
    # PowerShell accepts a backslash as a path separator on every platform, so a
    # relative `docs\series.toml` names the same file on Linux as on Windows.
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        (cwd / 'docs').mkdir()
        (cwd / 'docs' / 'series.toml').write_text('[series]\n', encoding='utf-8')
        b.created('gh pr create -R o/r', cwd, tool='PowerShell')
        cmd = "$env:KEEL_SERIES='docs\\series.toml'; gh pr create -R o/r --fill"
        assert decision(b.pre(cmd, cwd, tool='PowerShell')) == 'allow'


# ------------------------------------------------------ the working directory


def test_bash_cd_into_the_checkout_from_another_repo_is_denied():
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', target)
        assert decision(b.pre(f'cd {target.as_posix()} && gh pr create --fill', other)) == 'deny'
        assert decision(b.pre(f'cd "{target}"; gh pr create --fill', other)) == 'deny'
        assert decision(b.pre(f'cd {target.as_posix()}\ngh pr create --fill', other)) == 'deny'


def test_powershell_cd_quoted_into_the_checkout_is_denied():
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', target, tool='PowerShell')
        cmd = f'cd "{target}"; gh pr create --title t --body b'
        assert decision(b.pre(cmd, other, tool='PowerShell')) == 'deny'


def test_powershell_set_location_into_the_checkout_is_denied():
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', target)
        cmd = f"Set-Location -Path '{target}'; gh pr create --fill"
        assert decision(b.pre(cmd, other, tool='PowerShell')) == 'deny'


def test_bash_c_wrapper_with_an_inner_cd_is_denied():
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', target)
        cmd = f'bash -c "cd {target.as_posix()} && gh pr create --fill"'
        assert decision(b.pre(cmd, other)) == 'deny'


def test_powershell_command_wrapper_with_an_inner_cd_in_the_bash_tool_is_denied():
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', target)
        cmd = f'powershell -Command "cd {target}; gh pr create"'
        assert decision(b.pre(cmd, other)) == 'deny'


def test_pwsh_exe_wrapper_with_options_before_c_in_the_bash_tool_is_denied():
    with box() as b:
        target = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', target)
        assert decision(b.pre('pwsh.exe -NoProfile -c "gh pr create"', target)) == 'deny'
        cmd = 'echo start\npowershell.exe -NoProfile -Command "gh pr create -R o/r"'
        assert decision(b.pre(cmd, target)) == 'deny'


def test_relative_cd_resolves_against_the_payload_cwd():
    # R6-4: `cd ../or` from a sibling directory keys the create to o/r.
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', target)
        assert decision(b.pre('cd ../or && gh pr create --fill', other)) == 'deny'
        cmd = 'Set-Location ..\\or; gh pr create --fill'
        assert decision(b.pre(cmd, other, tool='PowerShell')) == 'deny'


def test_git_bash_and_home_paths_are_translated():
    with box() as b:
        other = b.repo('stack', 'https://github.com/me/stack.git')
        target = b.repo('home/or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', target)
        if os.name == 'nt':
            assert decision(b.pre(f'cd {msys(target)} && gh pr create', other)) == 'deny'
        assert decision(b.pre('cd ~/or && gh pr create', other)) == 'deny'
        assert decision(b.pre('cd ~; cd or; gh pr create', other)) == 'deny'


def test_a_directory_with_no_origin_is_not_keyed():
    with box() as b:
        plain = b.repo('plain', None)
        b.created('gh pr create', plain, url='https://github.com/o/r/pull/3')
        assert decision(b.pre('gh pr create --fill', plain)) == 'allow'


# ------------------------------------------------------------- mentions only


def test_mentions_in_arguments_heredocs_and_comments_are_ignored():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        for cmd in (
            'git commit -m "gh pr create"',
            "git commit -m 'docs: explain gh pr create'",
            'echo done  # then gh pr create',
            "cat > notes.md <<'EOF'\ngh pr create -R o/r\nEOF\n",
            'grep -n "gh pr create" README.md',
        ):
            assert decision(b.pre(cmd, cwd)) == 'allow', cmd
        assert not [e for e in b.log() if e.get('event') == 'PreToolUse'], b.log()


def test_create_after_a_shell_keyword_is_at_program_position():
    # Observed shape: a loop over repositories that opens one PR in each.
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        for cmd in (
            'if git diff --quiet; then echo same; else gh pr create -R o/r --fill; fi',
            'for r in a b; do gh pr create -R o/r --fill; done',
            'if ($true) { gh pr create -R o/r --fill }',
        ):
            tool = 'PowerShell' if cmd.startswith('if (') else 'Bash'
            assert decision(b.pre(cmd, cwd, tool=tool)) == 'deny', cmd


def test_create_after_a_heredoc_body_file_is_still_seen():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        cmd = (
            "cat > body.md <<'EOF'\n## What\nA change.\nEOF\n"
            'git push -u origin x && gh pr create -R o/r --body-file body.md'
        )
        assert decision(b.pre(cmd, cwd)) == 'deny'


def test_create_with_a_body_heredoc_inside_command_substitution_is_seen():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        cmd = 'gh pr create -R o/r --title t --body "$(cat <<\'EOF\'\nbody line\nEOF\n)"'
        assert decision(b.pre(cmd, cwd)) == 'deny'


# ------------------------------------------------------------------- modes


def test_off_switch_reads_and_writes_nothing():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd, mode='0')
        b.created('gh pr create -R o/r', cwd)
        proc = b.pre('gh pr create -R o/r', cwd, mode='0')
        assert decision(proc) == 'allow' and proc.stdout == b''
        assert len([e for e in b.log() if e.get('decision') == 'record']) == 1


def test_off_switch_records_nothing():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd, mode='0')
        assert not (b.data / 'series-guard').exists()
        assert decision(b.pre('gh pr create -R o/r', cwd)) == 'allow'


def test_observe_mode_logs_the_would_be_deny_and_prints_nothing():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd, mode='observe')
        proc = b.pre('gh pr create -R o/r', cwd, mode='observe')
        assert decision(proc) == 'allow' and proc.stdout == b''
        assert any(e.get('decision') == 'observe-deny' for e in b.log()), b.log()


# ------------------------------------------------------------ fails open


def test_malformed_payloads_exit_zero_with_no_output():
    with box() as b:
        for flag in ('--pre-tool-use', '--post-tool-use'):
            for raw in (b'not json', b'', b'[1, 2]', b'{"tool_input": "x"}', b'\xff\xfe'):
                proc = b.run(flag, None, raw=raw)
                assert proc.returncode == 0, (flag, raw, proc.stderr)
                assert proc.stdout == b'', (flag, raw, proc.stdout)


def test_a_non_shell_tool_is_ignored():
    with box() as b:
        cwd = b.repo('or', 'https://github.com/o/r.git')
        b.created('gh pr create -R o/r', cwd)
        payload = {
            'session_id': SESSION,
            'hook_event_name': 'PreToolUse',
            'cwd': str(cwd),
            'tool_name': 'Write',
            'tool_input': {'file_path': 'x.md', 'content': 'gh pr create -R o/r'},
        }
        assert decision(b.run('--pre-tool-use', payload)) == 'allow'


# ------------------------------------------------------------------ wiring


def _entries(event: str) -> list[dict]:
    manifest = json.loads(HOOKS_JSON.read_text(encoding='utf-8'))
    out = []
    for group in manifest['hooks'].get(event, []):
        for hook in group.get('hooks', []):
            if any('series_guard.py' in a for a in hook.get('args', [])):
                out.append({'matcher': group.get('matcher'), **hook})
    return out


def test_hooks_json_wires_both_arms_on_bash_and_powershell():
    for event, flag in (('PreToolUse', '--pre-tool-use'), ('PostToolUse', '--post-tool-use')):
        entries = _entries(event)
        assert len(entries) == 1, (event, entries)
        entry = entries[0]
        assert entry['matcher'] == 'Bash|PowerShell', entry
        assert entry['type'] == 'command' and entry['command'] == 'uv', entry
        assert entry['args'] == [
            'run',
            '--no-project',
            '--',
            'python',
            '${CLAUDE_PLUGIN_ROOT}/hooks/series_guard.py',
            flag,
        ], entry


if __name__ == '__main__':
    for _name, _fn in sorted(globals().items()):
        if _name.startswith('test_') and callable(_fn):
            _fn()
    print('ok: series_guard records created PRs per session and denies an undeclared second one')

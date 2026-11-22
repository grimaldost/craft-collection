#!/usr/bin/env python3
"""Checks of a home's permissions rendered from a policy, and of `kit run`'s comparison.

Contract under test, with the fake harness of `canary_fake_harness.py`:
- `kit home render --harness opencode --policy FILE`, for a test or a daily home:
  `opencode.jsonc`'s `permissions` are `* * DEFAULT`, the section's allow, ask and
  deny rules, then the four switches; its `policies` end with one `tool.use` deny
  `ACTION:RESOURCE` per deny rule; `home.json` gains `permissions_sha256`, the
  SHA-256 of the canonical JSON of both lists; a policy without the section, or no
  `--policy`, renders the switches alone;
- a section that would refuse either canary call (a deny of its command, a default
  `deny` with no allow for it) is refused at render with exit 64, nothing written
  and the rule named; a default `deny` with allows for both commands renders;
- `kit run` on an opencode home renders the lists again from its policy and refuses
  with exit 64 and no run: a section that would refuse a canary call (naming the
  rule), a home whose `permissions_sha256` differs (a policy changed after the
  render, the key edited or absent), and a home whose `opencode.jsonc` does not
  parse or holds other `permissions` or `policies`, a headless test home included;
- a Claude Code home renders and launches as before under a version 4 policy with
  any section.

Stdlib-runnable: `python test_permissions_launch.py`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.harnesses import opencode
from kit_fixtures import run_module
from test_daily_render import DAILY_TEXT
from test_launcher import Case, assert_refused, assert_started, kit, scratch

DENY_CMD = 'echo probe > deny-0123456789abcdef.marker'
ALLOW_CMD = 'echo probe > allow-0123456789abcdef.marker'
SECTION = (
    '\n[permissions]\ndefault = "ask"\n'
    '\n[[permissions.rule]]\naction = "shell"\nresource = "echo probe > perm-deny*"\n'
    'effect = "deny"\n'
    '\n[[permissions.rule]]\naction = "read"\nresource = "*"\neffect = "allow"\n'
    '\n[[permissions.rule]]\naction = "edit"\nresource = "*/locked/*"\neffect = "ask"\n'
    '\n[[permissions.rule]]\naction = "webfetch"\nresource = "*"\neffect = "deny"\n'
)
SWITCHES = [
    {'action': tool, 'resource': '*', 'effect': 'deny'}
    for tool in (
        'execute',
        'opencode_worktree_create',
        'opencode_session_move',
        'experimental_image_generate',
    )
]


def _st(action: str, resource: str, effect: str) -> dict:
    return {'action': action, 'resource': resource, 'effect': effect}


def _rule(action: str, resource: str, effect: str) -> str:
    return (
        f'\n[[permissions.rule]]\naction = "{action}"\nresource = {json.dumps(resource)}\n'
        f'effect = "{effect}"\n'
    )


def _policy(case: Case, name: str, section: str = SECTION, version: int = 4) -> Path:
    roots = json.dumps(str(case.tests))
    path = case.base / name
    path.write_text(
        f'version = {version}\n\n[launcher]\ntest_roots = [{roots}]\nforbidden_roots = []\n'
        + section,
        encoding='utf-8',
    )
    return path


def _render(case: Case, folder: Path, policy: Path | None, harness: str = 'opencode', *more):
    args = ['home', 'render', '--harness', harness, '--dir', str(folder)]
    args += list(more) or ['--endpoint', 'http://127.0.0.1:43210']
    args += ['--policy', str(policy)] if policy is not None else []
    return kit(case, *args)


def _config(folder: Path) -> dict:
    return json.loads((folder / 'conf' / 'opencode.jsonc').read_text(encoding='utf-8'))


def _home(folder: Path) -> dict:
    return json.loads((folder / 'home.json').read_text(encoding='utf-8'))


def _sha(config: dict) -> str:
    text = json.dumps(
        {'permissions': config['permissions'], 'policies': config['policies']},
        sort_keys=True,
        separators=(',', ':'),
    )
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _statements(folder: Path, provider: str = 'stub') -> list[dict]:
    kit_path = (folder / 'kit-shell' / 'opencode-plugin').as_posix()
    return opencode.rendered_policies(kit_path, provider)


def _done(case: Case) -> None:
    shutil.rmtree(case.base, ignore_errors=True)


# ---- the render


def test_a_rendered_opencode_home_holds_the_section_and_its_hash():
    case = Case(scratch(), 'opencode')
    try:
        folder = case.base / 'home-v4'
        proc = _render(case, folder, _policy(case, 'v4.toml'))
        assert proc.returncode == 0, proc.stderr
        config = _config(folder)
        assert config['permissions'] == [
            _st('*', '*', 'ask'),
            _st('read', '*', 'allow'),
            _st('edit', '*/locked/*', 'ask'),
            _st('shell', 'echo probe > perm-deny*', 'deny'),
            _st('webfetch', '*', 'deny'),
            *SWITCHES,
        ], config['permissions']
        assert config['policies'] == [
            *_statements(folder),
            _st('tool.use', 'shell:echo probe > perm-deny*', 'deny'),
            _st('tool.use', 'webfetch:*', 'deny'),
        ], config['policies']
        home = _home(folder)
        assert home['permissions_sha256'] == _sha(config), home
        assert json.loads(proc.stdout)['permissions_sha256'] == _sha(config)
    finally:
        _done(case)


def test_a_policy_without_the_section_renders_the_switches_alone():
    case = Case(scratch(), 'opencode')
    try:
        found = set()
        for name, policy in (
            ('none', None),
            ('v1', _policy(case, 'v1.toml', '', 1)),
            ('v4', _policy(case, 'v4-none.toml', '')),
        ):
            folder = case.base / f'home-{name}'
            proc = _render(case, folder, policy)
            assert proc.returncode == 0, (name, proc.stderr)
            config = _config(folder)
            assert config['permissions'] == SWITCHES, (name, config['permissions'])
            assert config['policies'] == _statements(folder), name
            assert _home(folder)['permissions_sha256'] == _sha(config), name
            found.add(json.dumps(config['permissions']))
        assert len(found) == 1
    finally:
        _done(case)


def test_a_daily_home_gains_the_section_and_its_hash():
    case = Case(scratch(), 'opencode')
    try:
        daily = case.base / 'daily.toml'
        daily.write_text(DAILY_TEXT, encoding='utf-8')
        folder = case.base / 'home-daily'
        policy = _policy(case, 'v4.toml')
        proc = _render(case, folder, policy, 'opencode', '--daily', str(daily))
        assert proc.returncode == 0, proc.stderr
        config = _config(folder)
        assert (
            config['permissions'][0] == _st('*', '*', 'ask')
            and config['permissions'][-4:] == SWITCHES
        )
        assert config['policies'][: len(_statements(folder, 'relay'))] == _statements(
            folder, 'relay'
        )
        assert config['policies'][-1] == _st('tool.use', 'webfetch:*', 'deny')
        assert _home(folder)['permissions_sha256'] == _sha(config)
    finally:
        _done(case)


def test_a_section_that_refuses_a_canary_call_is_refused_at_render():
    case = Case(scratch(), 'opencode')
    try:
        for n, (section, needle) in enumerate(
            (
                (
                    '\n[permissions]\ndefault = "allow"\n'
                    + _rule('shell', 'echo probe > allow*', 'deny'),
                    "'echo probe > allow*'",
                ),
                (
                    '\n[permissions]\ndefault = "ask"\n' + _rule('shell', 'echo *', 'deny'),
                    "'echo *'",
                ),
                ('\n[permissions]\ndefault = "deny"\n', 'default'),
                (
                    '\n[permissions]\ndefault = "deny"\n'
                    + _rule('shell', 'echo probe > deny-*', 'allow'),
                    'default',
                ),
            )
        ):
            folder = case.base / f'refused-{n}'
            proc = _render(case, folder, _policy(case, f'refused-{n}.toml', section))
            assert proc.returncode == 64, (n, proc.returncode, proc.stderr)
            assert needle in proc.stderr and 'canary' in proc.stderr, (n, proc.stderr)
            assert proc.stdout == '' and not (folder.exists() and any(folder.iterdir())), n
    finally:
        _done(case)


def test_a_default_deny_with_allows_for_both_canary_calls_renders():
    case = Case(scratch(), 'opencode')
    try:
        section = (
            '\n[permissions]\ndefault = "deny"\n'
            + _rule('shell', 'echo probe > perm-dda*', 'allow')
            + _rule('shell', 'echo probe > deny-*', 'allow')
            + _rule('shell', 'echo probe > allow-*', 'allow')
        )
        folder = case.base / 'home-dda'
        proc = _render(case, folder, _policy(case, 'dda.toml', section))
        assert proc.returncode == 0, proc.stderr
        assert _config(folder)['permissions'][0] == _st('*', '*', 'deny')
    finally:
        _done(case)


def test_a_claude_code_home_renders_as_before_under_any_section():
    case = Case(scratch(), 'claude-code')
    try:
        bad = '\n[permissions]\ndefault = "deny"\n' + _rule('shell', '*', 'deny')
        plain = case.base / 'cc-plain'
        assert _render(case, plain, None, 'claude-code').returncode == 0
        with_section = case.base / 'cc-section'
        proc = _render(case, with_section, _policy(case, 'bad.toml', bad), 'claude-code')
        assert proc.returncode == 0, proc.stderr
        assert list(_home(with_section)) == list(_home(plain)), _home(with_section)
        assert 'permissions_sha256' not in _home(with_section)
        settings = (with_section / 'claude-config' / 'settings.json').read_text(encoding='utf-8')
        want = (plain / 'claude-config' / 'settings.json').read_text(encoding='utf-8')
        assert settings == want.replace('cc-plain', 'cc-section'), settings
    finally:
        _done(case)


# ---- kit run


def _launch_case(section: str = SECTION) -> tuple[Case, Path]:
    """A case whose opencode home was rendered with a version 4 policy holding `section`."""
    case = Case(scratch(), 'opencode')
    policy = _policy(case, 'v4.toml', section)
    shutil.rmtree(case.home)
    proc = _render(case, case.home, policy)
    assert proc.returncode == 0, proc.stderr
    case.policy = policy
    return case, policy


def test_kit_run_launches_a_home_rendered_with_its_policy():
    case, _ = _launch_case()
    try:
        assert_started(case, case.run())
    finally:
        _done(case)


def test_kit_run_refuses_a_policy_changed_after_the_render():
    case, _ = _launch_case()
    try:
        case.policy = _policy(case, 'other.toml', SECTION.replace('"ask"', '"allow"', 1))
        assert_refused(case, case.run(), 'render')
        case.policy = _policy(case, 'v1.toml', '', 1)
        assert_refused(case, case.run(), 'render')
    finally:
        _done(case)


def test_kit_run_refuses_a_section_that_refuses_a_canary_call_naming_the_rule():
    case, _ = _launch_case()
    try:
        for section, needle in (
            (
                '\n[permissions]\ndefault = "ask"\n' + _rule('shell', 'echo probe > deny*', 'deny'),
                "'echo probe > deny*'",
            ),
            ('\n[permissions]\ndefault = "deny"\n', 'default'),
        ):
            case.policy = _policy(case, 'refusing.toml', section)
            assert_refused(case, case.run(), needle)
    finally:
        _done(case)


def test_kit_run_refuses_a_home_whose_configuration_holds_other_statements():
    for edit in ('permissions', 'policies', 'unparseable', 'missing'):
        case, _ = _launch_case()
        try:
            config_file = case.home / 'conf' / 'opencode.jsonc'
            if edit == 'unparseable':
                config_file.write_text(
                    config_file.read_text(encoding='utf-8') + '}', encoding='utf-8'
                )
            else:
                config = json.loads(config_file.read_text(encoding='utf-8'))
                if edit == 'permissions':
                    config['permissions'].insert(1, _st('shell', '*', 'allow'))
                elif edit == 'policies':
                    config['policies'] = config['policies'][:-1]
                else:
                    del config['permissions']
                config_file.write_text(json.dumps(config, indent=2), encoding='utf-8')
            assert_refused(case, case.run(), 'opencode.jsonc')
        finally:
            _done(case)


def test_kit_run_refuses_a_home_whose_recorded_hash_differs_or_is_absent():
    for edit in ('changed', 'absent'):
        case, _ = _launch_case()
        try:
            home = _home(case.home)
            if edit == 'changed':
                home['permissions_sha256'] = '0' * 64
            else:
                del home['permissions_sha256']
            (case.home / 'home.json').write_text(json.dumps(home, indent=2), encoding='utf-8')
            assert_refused(case, case.run(), 'render')
        finally:
            _done(case)


def test_a_claude_code_home_launches_under_any_section():
    case = Case(scratch(), 'claude-code')
    try:
        bad = '\n[permissions]\ndefault = "deny"\n' + _rule('shell', '*', 'deny')
        case.policy = _policy(case, 'bad.toml', bad)
        assert_started(case, case.run())
    finally:
        _done(case)


if __name__ == '__main__':
    run_module(globals(), 'permissions at render and kit run')

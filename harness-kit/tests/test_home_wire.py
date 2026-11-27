#!/usr/bin/env python3
"""Checks of `kit home wire`: the kit plugin wired into a copy of an opencode configuration.

Contract under test:
- `kit home wire --harness opencode --config FILE --shell-dir DIR --out FILE` reads an
  opencode global configuration (JSON or JSONC), materializes the opencode shell into DIR
  (absent or empty): `index.js` and a `shell_config.json` whose `cli_argv` ends in
  `judge --from opencode`, with no `note_config.json`, the same bytes a fresh
  `kit home render` writes into its shell folder;
- it writes to `--out` the configuration's text with two edits and every other byte kept,
  comments included: the shell folder (absolute, forward slashes) added to `plugins`,
  inserted as the first key after the opening brace when `plugins` is absent and appended
  when `plugins` is an array on one line, and `"update": "disable"` inserted the same way
  when `update` is absent;
- a `plugins` array spread over lines, a nested form, an unparseable text, an `--out` equal
  to `--config` and a non-empty DIR are refused with exit 64; a refusal over the
  configuration's form names the entry to add by hand, with the shell materialized for it;
  the configuration file is never written;
- `kit home wire --check --config FILE --shell-dir DIR` prints one line: `wired: CONFIG
  lists SHELL_DIR` and exit 0 when the configuration lists DIR and DIR's files equal what
  this kit renders, `not wired: REASON` and exit 1 otherwise, exit 64 for an unreadable
  configuration;
- the JSONC scanner blanks comments and trailing commas outside strings, keeping every
  offset and line break.

Stdlib-runnable: `python test_home_wire.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit.harnesses import opencode_wiring
from kit_fixtures import SRC, run_module

WINDOWS = os.name == 'nt'
ENDPOINT = 'http://127.0.0.1:43210'
SHELL_FILES = ('index.js', 'shell_config.json')

COMMENTED = """\
// The account's opencode configuration, with comments everywhere.
{
  /* the model */ "model": "stub/stub-model", // trailing note
  "plugins": [ "-unused" /* kept */ ], // one line
  "share": "a // not a comment",
  "quote": "say \\"/* not a comment */\\"",
  "providers": {
    "stub": { "models": { "m": {}, }, }, // trailing commas
  },
}
// after the object
"""


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    return env


def _kit(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=_env(),
        timeout=60,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _entry(folder: Path) -> str:
    return Path(os.path.abspath(str(folder))).as_posix()


class Case:
    """A configuration file, a shell folder and an output path in a fresh temporary folder."""

    def __init__(self, td: str, text: str | bytes) -> None:
        self.base = Path(td)
        self.config = self.base / 'account' / 'opencode.jsonc'
        self.config.parent.mkdir()
        data = text if isinstance(text, bytes) else text.encode('utf-8')
        self.config.write_bytes(data)
        self.before = _sha(self.config)
        self.dir = self.base / 'kit-shell'
        self.out = self.base / 'wired' / 'opencode.jsonc'

    @property
    def entry(self) -> str:
        return _entry(self.dir)

    def wire(self, *extra: str) -> subprocess.CompletedProcess:
        args = ['home', 'wire', '--harness', 'opencode', '--config', str(self.config)]
        args += ['--shell-dir', str(self.dir), '--out', str(self.out), *extra]
        proc = _kit(*args)
        assert _sha(self.config) == self.before, 'the configuration was written'
        return proc

    def wired(self) -> str:
        proc = self.wire()
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        assert proc.stdout == f'wired: {self.out} lists {self.dir}\n', proc.stdout
        return self.out.read_bytes().decode('utf-8')

    def check(self, config: Path | None = None) -> subprocess.CompletedProcess:
        target = str(config or self.out)
        return _kit('home', 'wire', '--check', '--config', target, '--shell-dir', str(self.dir))


def _subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(ch in it for ch in short)


def _load(text: str) -> dict:
    data = opencode_wiring.load_jsonc(text)
    assert isinstance(data, dict), data
    return data


def _assert_two_edits(before: str, after: str, entry: str, plugins_before: list | None) -> dict:
    """`after` is `before` with insertions only, and parses to its object plus the two edits."""
    assert _subsequence(before, after), (before, after)
    assert len(after) - len(before) <= len(entry) + 80, after
    old, new = _load(before), _load(after)
    want = dict(old)
    want['plugins'] = [*(plugins_before or []), entry]
    want.setdefault('update', 'disable')
    assert new == want, (new, want)
    return new


def _shell_files(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob('*'))
        if p.is_file()
    }


# ---- the scanner


def test_the_scanner_blanks_comments_and_trailing_commas_outside_strings():
    text = '{"a": "//x/*y*/", /* c\n d */ "b": [1, 2,], // e\n "c": {"d": 1,},}'
    out = opencode_wiring.strip_jsonc(text)
    assert len(out) == len(text) and out.count('\n') == text.count('\n'), out
    assert '"//x/*y*/"' in out and '/*' not in out.replace('"//x/*y*/"', ''), out
    assert json.loads(out) == {'a': '//x/*y*/', 'b': [1, 2], 'c': {'d': 1}}, out
    escaped = r'{"q": "a\"//b", "r": "\\"}'
    assert json.loads(opencode_wiring.strip_jsonc(escaped)) == {'q': 'a"//b', 'r': '\\'}


def test_the_scanner_refuses_an_unterminated_comment_or_string():
    for text in ('{"a": 1 /* open', '{"a": "open}', '{"a": 1} /'):
        try:
            opencode_wiring.load_jsonc(text)
        except opencode_wiring.JsoncError:
            continue
        raise AssertionError(f'parsed: {text!r}')


def test_the_scanner_keeps_a_comment_at_the_end_of_the_text():
    assert opencode_wiring.load_jsonc('{"a": 1} // end') == {'a': 1}
    assert opencode_wiring.load_jsonc('\ufeff{"a": 1}\r\n') == {'a': 1}


# ---- the two edits


def test_no_plugins_inserts_both_keys_first_after_the_brace():
    text = '{\n  // the model\n  "model": "stub/stub-model"\n}\n'
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, text)
        after = case.wired()
        new = _assert_two_edits(text, after, case.entry, None)
        assert list(new)[:2] == ['plugins', 'update'], list(new)
        line = json.dumps(case.entry)
        assert after == (
            '{\n  "plugins": [' + line + '],\n  "update": "disable",\n'
            '  // the model\n  "model": "stub/stub-model"\n}\n'
        ), after


def test_an_inline_and_an_empty_object():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{"model": "m"}')
        line = json.dumps(case.entry)
        assert case.wired() == '{"plugins": [' + line + '], "update": "disable", "model": "m"}'
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        after = case.wired()
        assert json.loads(after) == {'plugins': [case.entry], 'update': 'disable'}, after
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{\n}\n')
        after = case.wired()
        assert json.loads(after) == {'plugins': [case.entry], 'update': 'disable'}, after
        _assert_two_edits('{\n}\n', after, case.entry, None)


def test_a_one_line_array_gets_the_entry_appended():
    text = '{\n  "plugins": ["-other", "pkg"],\n  "model": "m"\n}\n'
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, text)
        after = case.wired()
        _assert_two_edits(text, after, case.entry, ['-other', 'pkg'])
        assert '["-other", "pkg", ' + json.dumps(case.entry) + ']' in after, after


def test_empty_and_trailing_comma_and_commented_arrays():
    for array, held in (
        ('[]', []),
        ('[ ]', []),
        ('["a",]', ['a']),
        ('["a", /* c */ ]', ['a']),
        ('[ /* the kit */ ]', []),
    ):
        text = '{"plugins": ' + array + ', "model": "m"}\n'
        with tempfile.TemporaryDirectory() as td:
            case = Case(td, text)
            after = case.wired()
            _assert_two_edits(text, after, case.entry, held)


def test_an_update_already_present_is_kept():
    text = '{\n  "update": "notify",\n  "plugins": [],\n  "model": "m"\n}\n'
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, text)
        after = case.wired()
        new = _assert_two_edits(text, after, case.entry, [])
        assert new['update'] == 'notify', new
        assert len(after) - len(text) == len(json.dumps(case.entry)), after


def test_comments_before_inside_and_after_the_edits_are_kept():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, COMMENTED)
        after = case.wired()
        _assert_two_edits(COMMENTED, after, case.entry, ['-unused'])
        for kept in ('// trailing note', '/* kept */', '// after the object', '/* the model */'):
            assert kept in after, kept
        assert after.startswith("// The account's opencode configuration"), after


def test_crlf_lines_stay_crlf():
    text = '{\r\n  "model": "m"\r\n}\r\n'
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, text)
        after = case.wired()
        _assert_two_edits(text, after, case.entry, None)
        assert after.count('\r\n') == after.count('\n') == 5, after


def test_a_byte_order_mark_and_non_ascii_text_are_kept():
    text = '\ufeff{\n  "name": "caf\u00e9"\n}\n'
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, text)
        after = case.wired()
        assert after.startswith('\ufeff{\n'), after
        _assert_two_edits(text, after, case.entry, None)


def test_the_output_folder_is_created_and_the_shell_materialized():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.wired()
        files = _shell_files(case.dir)
        assert sorted(files) == sorted(SHELL_FILES), sorted(files)
        config = json.loads(files['shell_config.json'])
        assert config['cli_argv'][-3:] == ['judge', '--from', 'opencode'], config
        assert not (case.dir / 'note_config.json').exists()


def test_the_shell_folder_equals_a_fresh_render_of_its_shell():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.wired()
        home = case.base / 'home'
        args = ['home', 'render', '--harness', 'opencode', '--dir', str(home)]
        proc = _kit(*args, '--endpoint', ENDPOINT)
        assert proc.returncode == 0, proc.stderr
        rendered = _shell_files(home / 'kit-shell' / 'opencode-plugin')
        assert _shell_files(case.dir) == rendered


# ---- refusals


def _assert_refused(case: Case, proc: subprocess.CompletedProcess, *, entry: bool) -> None:
    assert proc.returncode == 64, (proc.returncode, proc.stdout, proc.stderr)
    assert not case.out.exists(), 'the output was written'
    assert len(proc.stderr.splitlines()) == 1, proc.stderr
    if entry:
        assert json.dumps(case.entry) in proc.stderr, proc.stderr
        assert sorted(_shell_files(case.dir)) == sorted(SHELL_FILES), 'no shell for the entry'


def test_refused_plugins_forms_name_the_entry_to_add_by_hand():
    for text in (
        '{\n  "plugins": [\n    "a"\n  ]\n}\n',
        '{"plugins": [ "a", /* a comment\n over lines */ "b"]}',
        '{"plugins": [["pkg", {"option": 1}]]}',
        '{"plugins": [{"name": "pkg"}]}',
        '{"plugins": {"pkg": true}}',
        '{"plugins": "pkg"}',
        '{"plugins": [1]}',
        '{"agent": {"build": {"plugins": ["x"]}}}',
        '{"plugins": [], "plugins": []}',
        # Read as an empty array, but an appended entry would not read back.
        '{"plugins": [,]}',
    ):
        with tempfile.TemporaryDirectory() as td:
            case = Case(td, text)
            proc = case.wire()
            _assert_refused(case, proc, entry=True)
            assert 'plugins' in proc.stderr, (text, proc.stderr)


def test_each_plugins_refusal_names_its_reason():
    for text, reason in (
        ('{\n  "plugins": [\n    "a"\n  ]\n}\n', 'spans more than one line'),
        ('{"plugins": [["pkg", {"option": 1}]]}', 'nested form'),
        ('{"agent": {"build": {"plugins": ["x"]}}}', 'nested form'),
        ('{"plugins": [], "plugins": []}', 'more than once'),
    ):
        with tempfile.TemporaryDirectory() as td:
            case = Case(td, text)
            proc = case.wire()
            assert proc.returncode == 64 and reason in proc.stderr, (text, proc.stderr)


def test_an_unparseable_text_is_refused():
    for text in (
        '{"a": }',
        '{"a": 1',
        '{"a": 1 /* open',
        '[1, 2]',
        '"text"',
        '{"a": 1} {"b": 2}',
        '{"a": NaN}',
        '',
        b'{"a": "\xff"}',
    ):
        with tempfile.TemporaryDirectory() as td:
            case = Case(td, text)
            _assert_refused(case, case.wire(), entry=True)


def test_an_out_equal_to_the_config_is_refused_and_nothing_written():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        dotted = os.sep.join((str(case.config.parent), '.', case.config.name))
        spellings = [str(case.config), dotted]
        if WINDOWS:
            spellings.append(str(case.config).upper())
        for out in spellings:
            proc = _kit(
                'home',
                'wire',
                '--harness',
                'opencode',
                '--config',
                str(case.config),
                '--shell-dir',
                str(case.dir),
                '--out',
                out,
            )
            assert proc.returncode == 64, (out, proc.returncode, proc.stderr)
            assert _sha(case.config) == case.before
            assert not case.dir.exists(), 'the shell was materialized'


def test_a_non_empty_shell_folder_is_refused():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.dir.mkdir()
        (case.dir / 'other.txt').write_text('x', encoding='utf-8')
        _assert_refused(case, case.wire(), entry=False)
        assert sorted(_shell_files(case.dir)) == ['other.txt']
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.dir.write_text('a file', encoding='utf-8')
        _assert_refused(case, case.wire(), entry=False)


def test_an_out_inside_the_shell_folder_or_naming_a_folder_is_refused():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.out = case.dir / 'opencode.jsonc'
        proc = case.wire()
        assert proc.returncode == 64, (proc.returncode, proc.stderr)
        assert not case.dir.exists(), 'the shell was materialized'
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.out.mkdir(parents=True)
        proc = case.wire()
        assert proc.returncode == 64, (proc.returncode, proc.stderr)
        assert not case.dir.exists(), 'the shell was materialized'


def test_the_two_forms_take_their_own_options():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        args = ['home', 'wire', '--harness', 'opencode', '--config', str(case.config)]
        proc = _kit(*args, '--shell-dir', str(case.dir))
        assert proc.returncode == 2, (proc.returncode, proc.stderr)
        assert not case.dir.exists() and not case.out.exists()
        proc = _kit(*args, '--shell-dir', str(case.dir), '--out', str(case.out), '--check')
        assert proc.returncode == 2 and proc.stdout == '', (proc.returncode, proc.stdout)
        assert not case.dir.exists() and not case.out.exists()


def test_an_unreadable_config_and_another_harness_are_refused():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.config.unlink()
        case.before = ''
        proc = _kit(
            'home',
            'wire',
            '--harness',
            'opencode',
            '--config',
            str(case.config),
            '--shell-dir',
            str(case.dir),
            '--out',
            str(case.out),
        )
        assert proc.returncode == 64 and not case.out.exists(), proc.stderr
        assert not case.dir.exists(), 'the shell was materialized'
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        args = ['home', 'wire', '--harness', 'claude-code', '--config', str(case.config)]
        proc = _kit(*args, '--shell-dir', str(case.dir), '--out', str(case.out))
        assert proc.returncode == 64 and not case.out.exists(), proc.stderr
        assert not case.dir.exists()


# ---- --check


def test_check_says_wired_for_a_wired_copy():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, COMMENTED)
        case.wired()
        proc = case.check()
        assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
        assert proc.stdout == f'wired: {case.out} lists {case.dir}\n', proc.stdout
        # The --harness option is accepted as in the wiring form.
        args = ['home', 'wire', '--check', '--harness', 'opencode', '--config', str(case.out)]
        proc = _kit(*args, '--shell-dir', str(case.dir))
        assert proc.returncode == 0, proc.stdout


def test_check_says_not_wired_with_a_reason():
    def not_wired(case: Case, config: Path | None = None) -> None:
        proc = case.check(config)
        assert proc.returncode == 1, (proc.returncode, proc.stdout, proc.stderr)
        assert proc.stdout.startswith('not wired: '), proc.stdout
        assert len(proc.stdout.splitlines()) == 1, proc.stdout

    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{"plugins": ["a"]}')
        case.wired()
        not_wired(case, case.config)  # the original lists no shell folder
        removal = case.base / 'removal.jsonc'
        listed = {'plugins': [case.entry, '-harness-kit']}
        removal.write_text(json.dumps(listed), encoding='utf-8')
        not_wired(case, removal)  # a later entry removes the kit plugin
        removal.write_text(json.dumps({'plugins': ['-harness-kit', case.entry]}), 'utf-8')
        assert case.check(removal).returncode == 0  # an earlier removal is undone by the entry
        no_array = case.base / 'no-array.jsonc'
        no_array.write_text('{"model": "m"}', encoding='utf-8')
        not_wired(case, no_array)
        config = case.dir / 'shell_config.json'
        config.write_text(config.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        not_wired(case)  # the shell's files differ from what this kit renders
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.wired()
        (case.dir / 'note_config.json').write_text('{}', encoding='utf-8')
        not_wired(case)
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{}')
        case.wired()
        for name in SHELL_FILES:
            (case.dir / name).unlink()
        case.dir.rmdir()
        not_wired(case)


def test_check_refuses_an_unreadable_configuration():
    with tempfile.TemporaryDirectory() as td:
        case = Case(td, '{"a": }')
        for config in (case.config, case.base / 'absent.jsonc'):
            proc = case.check(config)
            assert proc.returncode == 64, (proc.returncode, proc.stdout, proc.stderr)
            assert proc.stdout == '', proc.stdout


if __name__ == '__main__':
    run_module(globals(), 'kit home wire')

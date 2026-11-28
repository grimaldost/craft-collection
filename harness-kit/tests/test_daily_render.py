#!/usr/bin/env python3
"""Checks of the daily file as a whole and of `kit home render --daily`.

Contract under test:
- a daily file is TOML with exactly `daily = 1`, the `[relay]` table and a `[git]` table with
  exactly `name` and `email`, non-empty strings without a line break; anything else is refused,
  naming the key;
- `load_daily` gives the file's absolute path, the SHA-256 of its bytes, its tables as parsed
  (`relay` and `git`), the relay settings and the identity;
- `changed_keys` names each dotted key whose value differs between two parsed documents, a key
  added or removed among them;
- the gitconfig text gives git the identity and an empty `credential.helper`;
- `kit home render --harness opencode --dir DIR --daily FILE` renders a daily home: the endpoint
  is `http://127.0.0.1:LISTEN_PORT`; `conf/opencode.jsonc` holds `update` `disable`, `model` and
  `small_model` `relay/DEFAULT_MODEL`, the kit plugin and one provider `relay` (name `Relay`,
  `env` `["KIT_RELAY_CAPABILITY"]`, the openai-compatible package, the endpoint plus `/v1`, one
  model per listed id); the home holds `gitconfig`; `home.json` gains `kind` `daily`,
  `daily_file`, `daily_sha256`, `daily_settings` and `canary_model`, and its render record names
  `gitconfig`;
- each model whose id starts with `anthropic/` carries `compatibility` `{"cacheFormat":
  "anthropic"}`, the value read from the driver's one constant, and every other model its name
  only; nothing renders a provider-level `compatibility`, a `settings.cache`, a ttl or a prompt
  cache option or key; those entries are the only difference they make to `conf/opencode.jsonc`,
  and in `home.json` only that file's render hash changes; a test home's stub model has none;
- `--endpoint` is refused with `--daily`, `--daily` is refused for `claude-code`, and a daily file
  that does not read is refused, each with exit 64 and nothing written; a test home gains `kind`
  `test` and `canary_model` `stub/stub-model`;
- a daily file whose `tools` table names a ripgrep renders a home whose
  `xdg/cache/opencode/bin/rg.exe` (`rg` off Windows, mode `0o755`) holds the named file's bytes,
  whose render record maps that path to the named hash and whose `daily_settings` holds the
  table, with no key in `home.json` that a home without it lacks; a named path that is absent, a
  folder, or a file of another SHA-256 exits 64 naming the path and leaves the target folder as
  it was, absent or empty; a daily file that names none renders no file under `xdg/cache`.

Every daily file here has `test = true` and a loopback upstream nothing listens on; nothing here
starts a relay or a harness.

Stdlib-runnable: `python test_daily_render.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import daily, harnesses
from harness_kit.harnesses import opencode
from kit_fixtures import SRC, run_module

ENDPOINT = 'http://127.0.0.1:43210'
# The numbers below are an example.
DAILY_TEXT = """\
daily = 1

[relay]
listen_port = 47910
upstream_base = "http://127.0.0.1:47911"
route = "/v1/chat/completions"
key_env = "TEST_DAILY_PROVIDER_KEY"
test = true
usage_include = true
default_model = "vendor/model-a"
upstream_timeout_s = 30

[relay.provider]
order = ["vendor"]
allow_fallbacks = false

[relay.ceilings]
run_usd = 1.5
day_usd = 4.0
month_usd = 20.0

[[relay.model]]
id = "vendor/model-a"
input_usd_per_mtok = 2.0
output_usd_per_mtok = 8.0
max_output_tokens = 1000

[[relay.model]]
id = "model-b"
input_usd_per_mtok = 0
output_usd_per_mtok = 0.5
max_output_tokens = 50

[git]
name = "Test Person"
email = "test.person@example.invalid"
"""


def _env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith('KIT_')}
    env.pop('PYTHONIOENCODING', None)
    env['PYTHONPATH'] = str(SRC)
    env.update(extra)
    return env


def _kit(base: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, '-m', 'harness_kit', *args],
        capture_output=True,
        text=True,
        encoding='utf-8',
        env=_env(KIT_STATE_ROOT=str(base / 'state')),
        cwd=str(base),
        timeout=60,
    )


def _file(base: Path, text: str = DAILY_TEXT) -> Path:
    path = base / 'daily.toml'
    path.write_text(text, encoding='utf-8')
    return path


def _refused(text: str, root: Path) -> str:
    with tempfile.TemporaryDirectory() as td:
        path = _file(Path(td), text)
        try:
            daily.load_daily(path, root)
        except daily.DailyError as exc:
            message = str(exc)
            assert message.isascii(), message
            return message
    raise AssertionError(f'accepted: {text!r}')


def _replace(old: str, new: str) -> str:
    assert old in DAILY_TEXT, old
    return DAILY_TEXT.replace(old, new, 1)


# ---- the daily file


def test_load_daily_gives_the_file_its_tables_and_the_identity():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        path = _file(base)
        got = daily.load_daily(path, base / 'state')
        assert got.path == Path(os.path.abspath(path)), got.path
        assert got.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
        parsed = tomllib.loads(DAILY_TEXT)
        assert got.settings == {'relay': parsed['relay'], 'git': parsed['git']}, got.settings
        assert got.relay.listen_port == 47910 and got.relay.default_model == 'vendor/model-a'
        assert (got.git_name, got.git_email) == ('Test Person', 'test.person@example.invalid')
        assert json.loads(json.dumps(got.settings)) == got.settings


def test_the_top_level_keys_are_exactly_daily_relay_and_git():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        assert 'daily' in _refused(_replace('daily = 1\n', ''), root)
        assert 'daily' in _refused(_replace('daily = 1\n', 'daily = 2\n'), root)
        assert 'daily' in _refused(_replace('daily = 1\n', 'daily = true\n'), root)
        assert 'extra' in _refused(_replace('daily = 1\n', 'daily = 1\nextra = 1\n'), root)
        assert 'git' in _refused(DAILY_TEXT.split('[git]')[0], root)
        assert 'relay' in _refused('daily = 1\n\n[git]\nname = "a"\nemail = "b"\n', root)


def test_the_git_table_holds_a_name_and_an_email_without_a_line_break():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        assert 'git.name' in _refused(_replace('name = "Test Person"\n', ''), root)
        assert 'git.email' in _refused(
            _replace('email = "test.person@example.invalid"\n', ''), root
        )
        assert 'git.signingkey' in _refused(DAILY_TEXT + 'signingkey = "x"\n', root)
        assert 'git.name' in _refused(_replace('"Test Person"', '""'), root)
        assert 'git.name' in _refused(_replace('"Test Person"', '1'), root)
        for brk in ('\\n', '\\r', '\\u2028', '\\u0085'):
            text = _replace('"Test Person"', f'"Test{brk}Person"')
            assert 'git.name' in _refused(text, root), brk
        assert 'git.email' in _refused(_replace('"test.person@', '"test\\nperson@'), root)


def test_an_invalid_relay_table_is_refused_naming_the_key():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / 'state'
        text = _replace('listen_port = 47910', 'listen_port = 80')
        assert 'relay.listen_port' in _refused(text, root)
        assert 'TOML' in _refused('[relay\n', root)


def test_changed_keys_names_each_dotted_key_whose_value_differs():
    old = tomllib.loads(DAILY_TEXT)
    old = {'relay': old['relay'], 'git': old['git']}
    new = json.loads(json.dumps(old))
    assert daily.changed_keys(old, new) == []
    new['relay']['ceilings']['day_usd'] = 5.0
    new['relay']['upstream_base'] = 'http://127.0.0.1:47999'
    assert daily.changed_keys(old, new) == ['relay.ceilings.day_usd', 'relay.upstream_base']
    new = json.loads(json.dumps(old))
    new['relay']['model'][1]['input_usd_per_mtok'] = 1.0
    del new['relay']['provider']['allow_fallbacks']
    new['git']['signingkey'] = 'x'
    assert daily.changed_keys(old, new) == [
        'git.signingkey',
        'relay.model[1].input_usd_per_mtok',
        'relay.provider.allow_fallbacks',
    ]
    new = json.loads(json.dumps(old))
    new['relay']['model'].append({'id': 'c'})
    assert daily.changed_keys(old, new) == ['relay.model'], daily.changed_keys(old, new)


def test_the_gitconfig_text_gives_git_the_identity_and_an_empty_helper():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'gitconfig'
        for name, email in (
            ('Test Person', 'test.person@example.invalid'),
            (' Quoted "Name" \\ #x; ', 'tab\there@example.invalid'),
        ):
            path.write_text(daily.gitconfig_text(name, email), encoding='utf-8')
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith('GIT_')}

            def get(key: str, env: dict = env) -> subprocess.CompletedProcess:
                return subprocess.run(  # noqa: S603 - fixed argv, no shell
                    ['git', 'config', '--file', str(path), '--get', key],  # noqa: S607
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    env=env,
                    check=False,
                )

            assert get('user.name').stdout == name + '\n', (name, get('user.name'))
            assert get('user.email').stdout == email + '\n', (email, get('user.email'))
            helper = get('credential.helper')
            assert helper.returncode == 0 and helper.stdout == '\n', helper


# ---- kit home render --daily


def test_render_daily_writes_the_relay_provider_the_gitconfig_and_the_home_keys():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        path = _file(base)
        home_dir = base / 'home'
        args = ['--harness', 'opencode', '--dir', str(home_dir), '--daily', str(path)]
        proc = _kit(base, 'home', 'render', *args)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        home = json.loads((home_dir / 'home.json').read_text(encoding='utf-8'))
        assert json.loads(proc.stdout) == home
        endpoint = 'http://127.0.0.1:47910'
        assert home['endpoint'] == endpoint, home
        config = json.loads((home_dir / 'conf' / 'opencode.jsonc').read_text(encoding='utf-8'))
        assert config['update'] == 'disable'
        assert config['model'] == config['small_model'] == 'relay/vendor/model-a', config
        assert config['plugins'] == [(home_dir / 'kit-shell' / 'opencode-plugin').as_posix()]
        assert list(config['providers']) == ['relay'], config['providers']
        relay = config['providers']['relay']
        assert relay['name'] == 'Relay' and relay['env'] == ['KIT_RELAY_CAPABILITY'], relay
        assert relay['package'] == '@opencode/ai/providers/openai-compatible', relay
        assert relay['settings'] == {'baseURL': endpoint + '/v1'}, relay
        assert sorted(relay['models']) == ['model-b', 'vendor/model-a'], relay['models']
        assert home['kind'] == 'daily'
        assert home['daily_file'] == os.path.abspath(path)
        assert home['daily_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()
        parsed = tomllib.loads(DAILY_TEXT)
        assert home['daily_settings'] == {'relay': parsed['relay'], 'git': parsed['git']}
        assert home['canary_model'] == 'relay/vendor/model-a'
        assert 'TEST_DAILY_PROVIDER_KEY' in json.dumps(home['daily_settings'])
        gitconfig = home_dir / 'gitconfig'
        assert gitconfig.read_text(encoding='utf-8') == daily.gitconfig_text(
            'Test Person', 'test.person@example.invalid'
        )
        record = home['rendered_sha256']
        assert record['gitconfig'] == hashlib.sha256(gitconfig.read_bytes()).hexdigest()
        assert 'conf/opencode.jsonc' in record and 'home.json' not in record, record


def test_render_refuses_endpoint_with_daily_daily_for_claude_code_and_a_bad_file():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        path = _file(base)
        bad = base / 'bad.toml'
        bad.write_text(_replace('daily = 1', 'daily = 3'), encoding='utf-8')
        cases = (
            (['--harness', 'opencode', '--daily', str(path), '--endpoint', ENDPOINT], '--endpoint'),
            (['--harness', 'claude-code', '--daily', str(path)], 'claude-code'),
            (['--harness', 'opencode', '--daily', str(bad)], 'daily'),
            (['--harness', 'opencode', '--daily', str(base / 'absent.toml')], 'daily'),
        )
        for i, (args, needle) in enumerate(cases):
            home_dir = base / f'home-{i}'
            proc = _kit(base, 'home', 'render', '--dir', str(home_dir), *args)
            assert proc.returncode == 64, (args, proc.returncode, proc.stderr)
            assert needle in proc.stderr and proc.stdout == '', (args, proc.stderr)
            assert not home_dir.exists(), args


def test_render_without_endpoint_or_daily_is_refused():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        proc = _kit(base, 'home', 'render', '--harness', 'opencode', '--dir', str(base / 'h'))
        assert proc.returncode != 0 and '--endpoint' in proc.stderr, proc.stderr
        assert not (base / 'h').exists()


def test_a_test_home_gains_its_kind_and_canary_model():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        home_dir = base / 'home'
        args = ['--harness', 'opencode', '--dir', str(home_dir), '--endpoint', ENDPOINT]
        proc = _kit(base, 'home', 'render', *args)
        assert proc.returncode == 0, proc.stderr
        home = json.loads((home_dir / 'home.json').read_text(encoding='utf-8'))
        assert home['kind'] == 'test' and home['canary_model'] == 'stub/stub-model', home
        assert not (home_dir / 'gitconfig').exists()
        config = json.loads((home_dir / 'conf' / 'opencode.jsonc').read_text(encoding='utf-8'))
        assert 'small_model' not in config and list(config['providers']) == ['stub'], config
        stub = config['providers']['stub']
        assert stub['models']['stub-model'] == {'name': 'Stub Model'}, stub['models']
        assert 'compatibility' not in stub and 'cache' not in stub['settings'], stub


# ---- the cache format of Anthropic models

ANTHROPIC = 'anthropic/claude-sonnet-5.5'
LOOKALIKE = 'openrouter/anthropic-like'
# Keys that would set a ttl or another cache option; none is rendered.
CACHE_OPTIONS = {'ttl', 'prompt_cache_options', 'prompt_cache_retention', 'prompt_cache_key'}


def _cached_text() -> str:
    """The example daily file with an Anthropic model and an id that only contains the word."""
    extra = ''.join(
        f'[[relay.model]]\nid = "{model_id}"\ninput_usd_per_mtok = 2.0\n'
        'output_usd_per_mtok = 10.0\nmax_output_tokens = 2000\n\n'
        for model_id in (ANTHROPIC, LOOKALIKE)
    )
    return _replace('[git]\n', extra + '[git]\n')


def _keys(value: object) -> set:
    """Every object key anywhere in a JSON value."""
    if isinstance(value, dict):
        return set(value).union(*(_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(v) for v in value))
    return set()


def test_render_daily_gives_each_anthropic_model_the_anthropic_cache_format():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        path = _file(base, _cached_text())
        home_dir = base / 'home'
        args = ['--harness', 'opencode', '--dir', str(home_dir), '--daily', str(path)]
        proc = _kit(base, 'home', 'render', *args)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        config = json.loads((home_dir / 'conf' / 'opencode.jsonc').read_text(encoding='utf-8'))
        relay = config['providers']['relay']
        models = relay['models']
        assert models[ANTHROPIC]['name'] == ANTHROPIC, models
        assert models[ANTHROPIC].get('compatibility') == {'cacheFormat': 'anthropic'}, models
        for model_id in (LOOKALIKE, 'vendor/model-a', 'model-b'):
            assert models[model_id]['name'] == model_id, models
            assert 'compatibility' not in models[model_id], (model_id, models)
        assert 'compatibility' not in relay and 'cache' not in relay['settings'], relay
        assert not _keys(config) & CACHE_OPTIONS, _keys(config) & CACHE_OPTIONS


def test_the_cache_format_value_is_read_from_the_drivers_constant():
    folder = Path(tempfile.mkdtemp(prefix='kit-render-'))
    saved = opencode.CACHE_FORMAT
    try:
        path = _file(folder, _cached_text())
        found = daily.load_daily(path, folder / 'state')
        opencode.CACHE_FORMAT = 'constant-under-test'
        home = harnesses.get('opencode').render_daily_home(folder / 'home', found)
        config = json.loads(Path(home['config_file']).read_text(encoding='utf-8'))
        entry = config['providers']['relay']['models'][ANTHROPIC]
        assert entry['compatibility'] == {'cacheFormat': 'constant-under-test'}, entry
    finally:
        opencode.CACHE_FORMAT = saved
        shutil.rmtree(folder, ignore_errors=True)


def _strip_compatibility(config: dict) -> dict:
    copy = json.loads(json.dumps(config))
    for entry in copy['providers']['relay']['models'].values():
        entry.pop('compatibility', None)
    return copy


def test_the_cache_format_changes_only_the_model_entries_and_the_config_hash():
    folder = Path(tempfile.mkdtemp(prefix='kit-render-'))
    saved = opencode.model_entry
    try:
        path = _file(folder, _cached_text())
        found = daily.load_daily(path, folder / 'state')
        home_dir = folder / 'home'
        driver = harnesses.get('opencode')
        renders = []
        for entry in (saved, lambda model_id: {'name': model_id}):
            shutil.rmtree(home_dir, ignore_errors=True)
            opencode.model_entry = entry
            home = driver.render_daily_home(home_dir, found)
            text = Path(home['config_file']).read_text(encoding='utf-8')
            on_disk = json.loads((home_dir / 'home.json').read_text(encoding='utf-8'))
            renders.append((json.loads(text), on_disk))
        (marked, marked_home), (plain, plain_home) = renders
        assert marked != plain, 'the render carries no cache format'
        assert _strip_compatibility(marked) == plain
        marked_hashes = dict(marked_home.pop('rendered_sha256'))
        plain_hashes = dict(plain_home.pop('rendered_sha256'))
        config_key = 'conf/opencode.jsonc'
        assert marked_hashes.pop(config_key) != plain_hashes.pop(config_key)
        assert marked_hashes == plain_hashes, (marked_hashes, plain_hashes)
        assert marked_home['permissions_sha256'] == plain_home['permissions_sha256']
        assert marked_home == plain_home, (marked_home, plain_home)
    finally:
        opencode.model_entry = saved
        shutil.rmtree(folder, ignore_errors=True)


# ---- the named ripgrep

WINDOWS = os.name == 'nt'
COPY = 'xdg/cache/opencode/bin/' + ('rg.exe' if WINDOWS else 'rg')
# A stand-in for a ripgrep binary: the render copies and hashes it and never runs it.
STAND_IN = b'MZ stand-in for a ripgrep binary\x00\x01\x02' * 64


def _toml(value: str) -> str:
    return '"' + value.replace('\\', '\\\\') + '"'


def _named(base: Path, source: Path, sha: str | None = None) -> Path:
    digest = sha or hashlib.sha256(source.read_bytes()).hexdigest()
    table = f'\n[tools]\nripgrep = {_toml(str(source))}\nripgrep_sha256 = "{digest}"\n'
    return _file(base, DAILY_TEXT + table)


def _render_daily(base: Path, path: Path, home_dir: Path) -> subprocess.CompletedProcess:
    args = ['--harness', 'opencode', '--dir', str(home_dir), '--daily', str(path)]
    return _kit(base, 'home', 'render', *args)


def test_render_copies_the_named_ripgrep_into_the_home():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        source = base / 'tools' / 'rg-source.bin'
        source.parent.mkdir()
        source.write_bytes(STAND_IN)
        sha = hashlib.sha256(STAND_IN).hexdigest()
        home_dir = base / 'home'
        proc = _render_daily(base, _named(base, source), home_dir)
        assert proc.returncode == 0, (proc.returncode, proc.stderr)
        copy = home_dir / COPY
        assert copy.read_bytes() == STAND_IN
        if not WINDOWS:
            assert copy.stat().st_mode & 0o777 == 0o755, oct(copy.stat().st_mode)
        assert sorted(p.name for p in copy.parent.iterdir()) == [copy.name]
        home = json.loads((home_dir / 'home.json').read_text(encoding='utf-8'))
        assert home['rendered_sha256'][COPY] == sha, home['rendered_sha256']
        assert home['daily_settings']['tools'] == {
            'ripgrep': str(source),
            'ripgrep_sha256': sha,
        }, home['daily_settings']
        plain_dir = base / 'plain'
        proc = _render_daily(base, _file(base), plain_dir)
        assert proc.returncode == 0, proc.stderr
        plain = json.loads((plain_dir / 'home.json').read_text(encoding='utf-8'))
        assert list(home) == list(plain), (list(home), list(plain))
        assert 'tools' not in plain['daily_settings'], plain['daily_settings']
        assert COPY not in plain['rendered_sha256'], plain['rendered_sha256']
        assert not (plain_dir / 'xdg' / 'cache').exists()
        assert source.read_bytes() == STAND_IN, 'the source changed'


def test_a_missing_folder_or_other_ripgrep_is_refused_and_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        source = base / 'rg-source.bin'
        source.write_bytes(STAND_IN)
        sha = hashlib.sha256(STAND_IN).hexdigest()
        folder = base / 'a-folder'
        folder.mkdir()
        other = 'f' * 64
        cases = (
            (base / 'absent.bin', sha, ['absent.bin', 'FileNotFoundError']),
            (folder, sha, ['a-folder', 'not a regular file']),
            (source, other, ['rg-source.bin', f'has SHA-256 {sha}', f'ripgrep_sha256 {other}']),
        )
        for i, (path, digest, needles) in enumerate(cases):
            daily_file = _named(base, path, digest)
            for existed in (False, True):
                home_dir = base / f'home-{i}-{existed}'
                if existed:
                    home_dir.mkdir()
                proc = _render_daily(base, daily_file, home_dir)
                assert proc.returncode == 64, (path, proc.returncode, proc.stderr)
                assert proc.stdout == '', proc.stdout
                for needle in needles:
                    assert needle in proc.stderr, (needle, proc.stderr)
                if existed:
                    assert home_dir.is_dir() and not any(home_dir.iterdir()), path
                else:
                    assert not home_dir.exists(), path


def test_the_render_writes_the_bytes_it_hashed_and_reads_the_source_once():
    folder = Path(tempfile.mkdtemp(prefix='kit-render-'))
    saved = Path.read_bytes
    reads = []
    try:
        source = folder / 'rg-source.bin'
        source.write_bytes(STAND_IN)
        found = daily.load_daily(_named(folder, source), folder / 'state')

        def spy(self: Path) -> bytes:
            data = saved(self)
            if self == source:
                reads.append(self)
                source.write_bytes(b'replaced after the read')
            return data

        Path.read_bytes = spy  # type: ignore[method-assign]
        home = harnesses.get('opencode').render_daily_home(folder / 'home', found)
        Path.read_bytes = saved  # type: ignore[method-assign]
        assert len(reads) == 1, reads
        assert (folder / 'home' / COPY).read_bytes() == STAND_IN
        assert home['rendered_sha256'][COPY] == hashlib.sha256(STAND_IN).hexdigest()
    finally:
        Path.read_bytes = saved  # type: ignore[method-assign]
        shutil.rmtree(folder, ignore_errors=True)


if __name__ == '__main__':
    run_module(globals(), 'the daily file and the daily render')

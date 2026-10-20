"""Tests for hook_log. Runnable with pytest or `python test_hook_log.py`."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
from pathlib import Path

import hook_log

STATE_KEYS = (hook_log.STATE_DIR_ENV, 'CLAUDE_PLUGIN_DATA')
HOME_KEYS = ('HOME', 'USERPROFILE')
ENV_KEYS = (*STATE_KEYS, *HOME_KEYS, 'CLAUDE_CONFIG_DIR')


@contextlib.contextmanager
def _env(home=None, **values):
    """Set (or, with None, unset) the state-dir variables; restore them after.

    HOME and USERPROFILE point at `home`, or at a fresh empty directory, so a
    test can never read the real machine's plugin data; CLAUDE_CONFIG_DIR is
    unset unless given.
    """
    saved = {k: os.environ.get(k) for k in ENV_KEYS}
    with tempfile.TemporaryDirectory() as empty_home:
        try:
            for k in ENV_KEYS:
                os.environ.pop(k, None)
            for k in HOME_KEYS:
                os.environ[k] = str(home or empty_home)
            for k, v in values.items():
                if v is not None:
                    os.environ[k] = v
            yield
        finally:
            _restore(saved)


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _lines(d):
    path = Path(d) / hook_log.LOG_NAME
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines() if x.strip()]


def test_override_is_honoured():
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as data:
        with _env(**{hook_log.STATE_DIR_ENV: d, 'CLAUDE_PLUGIN_DATA': data}):
            assert hook_log.state_dir() == Path(d)
            hook_log.append({'hook': 'uv_enforce'})
        assert len(_lines(d)) == 1
        assert _lines(data) == []


def test_plugin_data_dir_is_the_fallback():
    with tempfile.TemporaryDirectory() as data:
        with _env(CLAUDE_PLUGIN_DATA=data):
            assert hook_log.state_dir() == Path(data)
            hook_log.append({'hook': 'ruff_format'})
        assert [r['hook'] for r in _lines(data)] == ['ruff_format']


def test_system_temp_dir_is_the_last_fallback():
    # Path only: a test never writes to the real temp-dir log.
    with _env():
        expected = Path(tempfile.gettempdir()) / 'engineering-discipline'
        assert hook_log.state_dir() == expected


def test_append_writes_one_json_line_with_a_timestamp():
    with tempfile.TemporaryDirectory() as d, _env(**{hook_log.STATE_DIR_ENV: d}):
        hook_log.append({'hook': 'uv_enforce', 'verdict': 'block'})
        hook_log.append({'hook': 'ruff_format', 'files': 2})
        records = _lines(d)
    assert [r['hook'] for r in records] == ['uv_enforce', 'ruff_format']
    assert all(isinstance(r['ts'], str) and r['ts'].endswith('Z') for r in records)


def test_cap_stops_growth():
    with tempfile.TemporaryDirectory() as d, _env(**{hook_log.STATE_DIR_ENV: d}):
        path = Path(d) / hook_log.LOG_NAME
        path.write_text('x' * (hook_log.CAP_BYTES - 1), encoding='utf-8')
        hook_log.append({'hook': 'uv_enforce'})
        size = path.stat().st_size
        assert size > hook_log.CAP_BYTES - 1  # under the cap, one more line lands
        hook_log.append({'hook': 'uv_enforce'})
        assert path.stat().st_size == size  # at or over the cap, nothing more


def test_unwritable_state_dir_is_swallowed():
    with tempfile.TemporaryDirectory() as d:
        blocker = Path(d) / 'a-file'
        blocker.write_text('', encoding='utf-8')
        with _env(**{hook_log.STATE_DIR_ENV: str(blocker)}):
            hook_log.append({'hook': 'uv_enforce'})  # must not raise


def test_count_prints_counts_per_hook_and_skips_corrupt_lines():
    with tempfile.TemporaryDirectory() as d, _env(**{hook_log.STATE_DIR_ENV: d}):
        hook_log.append({'hook': 'uv_enforce'})
        hook_log.append({'hook': 'uv_enforce'})
        hook_log.append({'hook': 'ruff_format'})
        with (Path(d) / hook_log.LOG_NAME).open('a', encoding='utf-8') as fh:
            fh.write('not json\n[1]\n')
        assert hook_log.counts() == {'ruff_format': 1, 'uv_enforce': 2}
        for argv in ([], ['--count']):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert hook_log.main(argv) == 0
            text = out.getvalue()
            assert 'uv_enforce: 2' in text, text
            assert 'ruff_format: 1' in text, text


def test_count_skips_a_line_that_is_not_utf8():
    with tempfile.TemporaryDirectory() as d, _env(**{hook_log.STATE_DIR_ENV: d}):
        (Path(d) / hook_log.LOG_NAME).write_bytes(
            b'{"hook":"uv_enforce"}\n\xff\xfe garbage\n{"hook":"uv_enforce"}\n'
        )
        assert hook_log.counts() == {'uv_enforce': 2}
        with contextlib.redirect_stdout(io.StringIO()):
            assert hook_log.main([]) == 0


def test_count_with_no_log_yet():
    with tempfile.TemporaryDirectory() as d, _env(**{hook_log.STATE_DIR_ENV: d}):
        assert hook_log.counts() == {}
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert hook_log.main(['--count']) == 0
        assert 'no firings' in out.getvalue()


def _write_log(config_dir, marketplace, *hooks):
    """Create <config_dir>/plugins/data/engineering-discipline-<marketplace>/hook-log.ndjson."""
    path = (
        Path(config_dir)
        / 'plugins'
        / 'data'
        / f'engineering-discipline-{marketplace}'
        / hook_log.LOG_NAME
    )
    path.parent.mkdir(parents=True)
    path.write_text(''.join(json.dumps({'hook': h}) + chr(10) for h in hooks), encoding='utf-8')
    return path


def _run_cli(argv=()):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert hook_log.main(list(argv)) == 0
    return out.getvalue()


def test_cli_reads_plugin_data_under_home_when_no_variable_is_set():
    with tempfile.TemporaryDirectory() as home:
        log = _write_log(Path(home) / '.claude', 'x', 'uv_enforce', 'ruff_format')
        with _env(home=home):
            text = _run_cli()
        assert str(log) in text, text
        assert 'uv_enforce: 1' in text, text
        assert 'ruff_format: 1' in text, text
        assert 'no firings' not in text, text


def test_cli_reads_every_marketplace_directory():
    with tempfile.TemporaryDirectory() as home:
        first = _write_log(Path(home) / '.claude', 'a', 'uv_enforce', 'uv_enforce')
        second = _write_log(Path(home) / '.claude', 'b', 'ruff_format')
        with _env(home=home):
            text = _run_cli(['--count'])
        assert str(first) in text and str(second) in text, text
        assert text.index(str(first)) < text.index('uv_enforce: 2') < text.index(str(second)), text
        assert 'ruff_format: 1' in text, text


def test_cli_says_so_for_an_empty_plugin_data_log():
    with tempfile.TemporaryDirectory() as home:
        empty = _write_log(Path(home) / '.claude', 'a')
        full = _write_log(Path(home) / '.claude', 'b', 'uv_enforce')
        with _env(home=home):
            text = _run_cli()
        assert str(empty) in text and str(full) in text, text
        assert text.index('no firings logged yet') < text.index('uv_enforce: 1'), text


def test_claude_config_dir_overrides_home():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as config:
        _write_log(Path(home) / '.claude', 'home', 'ruff_format')
        log = _write_log(config, 'cfg', 'uv_enforce')
        with _env(home=home, CLAUDE_CONFIG_DIR=config):
            text = _run_cli()
        assert str(log) in text, text
        assert 'uv_enforce: 1' in text, text
        assert 'ruff_format' not in text, text


def test_cli_falls_back_to_the_temp_directory_without_plugin_data():
    with tempfile.TemporaryDirectory() as home:
        (Path(home) / '.claude' / 'plugins' / 'data').mkdir(parents=True)
        with _env(home=home):
            text = _run_cli()
        expected = Path(tempfile.gettempdir()) / 'engineering-discipline' / hook_log.LOG_NAME
        assert f'log: {expected}' in text, text


def test_a_set_variable_ignores_plugin_data_under_home():
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as data:
        _write_log(Path(home) / '.claude', 'x', 'ruff_format')
        for key in (hook_log.STATE_DIR_ENV, 'CLAUDE_PLUGIN_DATA'):
            with _env(home=home, **{key: data}):
                text = _run_cli()
            assert f'log: {Path(data) / hook_log.LOG_NAME}' in text, text
            assert 'ruff_format' not in text, text
            assert 'no firings logged yet' in text, text


def test_cli_output_stays_ascii_for_a_non_ascii_path():
    with tempfile.TemporaryDirectory() as home:
        _write_log(Path(home) / '.claude', 'caf\u00e9', 'uv_enforce')
        with _env(home=home):
            text = _run_cli()
        text.encode('ascii')
        assert '\\xe9' in text, text


if __name__ == '__main__':
    for name, fn in list(globals().items()):
        if name.startswith('test_') and callable(fn):
            fn()
    print('ok: all hook_log tests passed')

#!/usr/bin/env python3
"""Checks of the daily file's `[relay]` table as `daily.py` reads it.

Contract under test:
- a valid table gives its settings: the port, the upstream, the route, the key's variable, the
  test switch, the usage switch, the default model, the timeout, the provider object, the three
  ceilings and the priced models;
- an unknown key, a wrong type or a value out of range is refused, naming the key;
- with `test` true the upstream is `http://127.0.0.1:PORT` only; with `test` false it is an
  `https` URL, and the file is refused while the state root lies under the temporary folder;
- `key_env` is refused unless the secret-name rule matches it, and when it is `PATH`, a name of
  the launcher's allow list or a name the launcher or a driver sets in a session.

No daily file here has `test` false and a state root outside the temporary folder, and nothing
here binds a port or sends a request.

Stdlib-runnable: `python test_daily.py`.
"""

from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from harness_kit import daily
from kit_fixtures import run_module

# A state root outside the temporary folder, never created: only `test = true` tables use it.
ELSEWHERE = Path(os.path.abspath('/home/user/kit-state'))
TEMP_ROOT = Path(tempfile.gettempdir()) / 'kit-daily-test-root'
# An https upstream no request can reach; only tables with a state root under TEMP_ROOT use it.
HTTPS_LOOPBACK = 'https://127.0.0.1:1'
# The numbers below are an example.
TABLE = {
    'listen_port': 47900,
    'upstream_base': 'http://127.0.0.1:47901',
    'route': '/v1/chat/completions',
    'key_env': 'TEST_PROVIDER_KEY',
    'test': True,
    'usage_include': True,
    'default_model': 'vendor/model-a',
    'upstream_timeout_s': 30,
    'provider': {'order': ['vendor'], 'allow_fallbacks': False, 'data_collection': 'deny'},
    'ceilings': {'run_usd': 1.5, 'day_usd': 4, 'month_usd': 20.0},
    'model': [
        {
            'id': 'vendor/model-a',
            'input_usd_per_mtok': 2.0,
            'output_usd_per_mtok': 8,
            'max_output_tokens': 1000,
        },
        {
            'id': 'vendor/model-b',
            'input_usd_per_mtok': 0,
            'output_usd_per_mtok': 0.5,
            'max_output_tokens': 50,
        },
    ],
}


def table(**over: object) -> dict:
    """The valid table with dotted keys replaced; a value of `...` removes the key."""
    data = copy.deepcopy(TABLE)
    for dotted, value in over.items():
        node = data
        *parents, leaf = dotted.split('.')
        for key in parents:
            node = node[int(key)] if isinstance(node, list) else node[key]
        if value is ...:
            del node[leaf]
        else:
            node[leaf] = value
    return data


def refused(data: object, root: Path = ELSEWHERE) -> str:
    try:
        daily.check_relay(data, root)
    except daily.DailyError as exc:
        text = str(exc)
        assert text.isascii(), text
        return text
    raise AssertionError(f'accepted: {data!r}')


def test_a_valid_table_gives_its_settings():
    got = daily.check_relay(table(), ELSEWHERE)
    assert got.listen_port == 47900
    assert got.upstream_base == 'http://127.0.0.1:47901'
    assert got.route == '/v1/chat/completions'
    assert got.key_env == 'TEST_PROVIDER_KEY'
    assert got.test is True and got.usage_include is True
    assert got.default_model == 'vendor/model-a'
    assert got.upstream_timeout_s == 30
    assert got.provider == {
        'order': ['vendor'],
        'allow_fallbacks': False,
        'data_collection': 'deny',
    }
    assert (got.run_usd, got.day_usd, got.month_usd) == (1.5, 4, 20.0)
    model = got.model('vendor/model-b')
    assert model is not None and model.max_output_tokens == 50, model
    assert (model.input_usd_per_mtok, model.output_usd_per_mtok) == (0, 0.5)
    assert got.model('vendor/model-c') is None


def test_the_provider_table_is_optional():
    got = daily.check_relay(table(provider=...), ELSEWHERE)
    assert got.provider is None


def test_an_unknown_key_is_refused_naming_it():
    assert 'relay.extra' in refused(table(extra=1))
    assert 'relay.ceilings.week_usd' in refused(table(**{'ceilings.week_usd': 1.0}))
    assert 'relay.provider.only' in refused(table(**{'provider.only': ['x']}))
    assert 'relay.model' in refused(table(**{'model.0.alias': 'a'}))


def test_a_missing_key_is_refused_naming_it():
    for key in ('listen_port', 'upstream_base', 'route', 'key_env', 'test', 'usage_include'):
        assert f'relay.{key}' in refused(table(**{key: ...})), key
    for key in ('default_model', 'upstream_timeout_s', 'ceilings', 'model'):
        assert f'relay.{key}' in refused(table(**{key: ...})), key
    assert 'relay.ceilings.day_usd' in refused(table(**{'ceilings.day_usd': ...}))
    assert 'max_output_tokens' in refused(table(**{'model.1.max_output_tokens': ...}))


def test_a_wrong_type_is_refused_naming_the_key():
    cases = {
        'listen_port': '47900',
        'test': 'true',
        'usage_include': 1,
        'route': 5,
        'key_env': ['TEST_PROVIDER_KEY'],
        'upstream_timeout_s': True,
        'ceilings.run_usd': '1.0',
        'ceilings.day_usd': True,
        'provider.order': 'vendor',
        'provider.allow_fallbacks': 'no',
        'model.0.max_output_tokens': 10.5,
        'model.0.input_usd_per_mtok': '2',
    }
    for dotted, value in cases.items():
        assert dotted.split('.')[-1] in refused(table(**{dotted: value})), dotted
    assert 'relay' in refused('not a table')
    assert 'relay.model' in refused(table(model={'id': 'x'}))


def test_a_value_out_of_range_is_refused():
    cases = {
        'listen_port': 80,
        'ceilings.run_usd': 0,
        'ceilings.month_usd': -1.0,
        'upstream_timeout_s': 0,
        'model.0.max_output_tokens': 0,
        'model.1.output_usd_per_mtok': -0.1,
        'provider.data_collection': 'sometimes',
        'route': 'v1/chat/completions',
    }
    for dotted, value in cases.items():
        assert dotted.split('.')[-1] in refused(table(**{dotted: value})), dotted
    assert 'listen_port' in refused(table(listen_port=65536))
    assert 'route' in refused(table(route='/v1/chat completions'))
    assert 'route' in refused(table(route='/v1/chat?x=1'))
    assert 'ceilings' in refused(table(**{'ceilings.day_usd': float('nan')}))


def test_the_default_model_is_one_of_the_listed_ids():
    assert 'relay.default_model' in refused(table(default_model='vendor/model-z'))
    assert 'relay.model' in refused(table(model=[]))
    same = table()
    same['model'][1]['id'] = 'vendor/model-a'
    assert 'vendor/model-a' in refused(same)


def test_a_test_upstream_is_loopback_http_only():
    assert daily.check_relay(table(upstream_base='http://127.0.0.1:80'), ELSEWHERE)
    for value in (
        'http://localhost:47901',
        'http://10.0.0.1:47901',
        'http://relay-upstream.invalid:47901',
        'https://127.0.0.1:1',
        'http://127.0.0.1',
        'http://127.0.0.1:0',
        'http://user@127.0.0.1:47901',
    ):
        assert 'relay.upstream_base' in refused(table(upstream_base=value)), value


def test_a_non_test_upstream_is_https_only():
    for value in ('http://127.0.0.1:1', 'http://relay-upstream.invalid/api', 'ftp://x.invalid'):
        text = refused(table(upstream_base=value, test=False), TEMP_ROOT)
        assert 'relay.upstream_base' in text and 'https' in text, (value, text)


def test_test_false_is_refused_while_the_state_root_lies_under_the_temporary_folder():
    base = 'https' + '://relay-upstream.invalid/api'
    text = refused(table(upstream_base=base, test=False), TEMP_ROOT)
    assert 'temporary folder' in text and 'relay.test' in text, text
    text = refused(table(upstream_base=HTTPS_LOOPBACK, test=False), TEMP_ROOT)
    assert 'temporary folder' in text, text
    inside = Path(tempfile.gettempdir())
    assert 'temporary folder' in refused(table(upstream_base=base, test=False), inside)


def test_key_env_must_match_the_secret_name_rule():
    for name in ('TEST_PROVIDER', 'KEY_FILE', 'PROVIDER_KEYS', '', '1_KEY', 'A-B_KEY'):
        assert 'relay.key_env' in refused(table(key_env=name)), name
    for name in ('TEST_PROVIDER_KEY', 'OTHER_TOKEN', 'X_SECRET', 'Y_PASSWORD', 'GH_THING'):
        assert daily.check_relay(table(key_env=name), ELSEWHERE).key_env == name


def test_key_env_is_never_a_name_a_session_receives():
    for name in ('PATH', 'USERNAME', 'STUB_API_KEY', 'stub_api_key', 'ANTHROPIC_AUTH_TOKEN'):
        assert 'relay.key_env' in refused(table(key_env=name)), name
    names = daily.session_names()
    for name in ('PATH', 'USERNAME', 'SYSTEMROOT', 'STUB_API_KEY', 'KIT_POLICY', 'HTTPS_PROXY'):
        assert name in names, name


def test_load_relay_reads_a_daily_file():
    text = """\
daily = 1

[relay]
listen_port = 47900
upstream_base = "http://127.0.0.1:47901"
route = "/v1/chat/completions"
key_env = "TEST_PROVIDER_KEY"
test = true
usage_include = false
default_model = "vendor/model-a"
upstream_timeout_s = 2.5

[relay.ceilings]
run_usd = 1.0
day_usd = 2.0
month_usd = 3.0

[[relay.model]]
id = "vendor/model-a"
input_usd_per_mtok = 1.0
output_usd_per_mtok = 2.0
max_output_tokens = 100

[git]
name = "Test Person"
email = "test@example.invalid"
"""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / 'daily.toml'
        path.write_text(text, encoding='utf-8')
        got = daily.load_relay(path, Path(td) / 'state')
        assert got.upstream_timeout_s == 2.5 and got.provider is None and not got.usage_include
        for broken, word in (
            ('[relay\n', 'TOML'),
            ('daily = 1\n', 'relay'),
            ('relay = 1\n', 'relay'),
        ):
            path.write_text(broken, encoding='utf-8')
            try:
                daily.load_relay(path, Path(td) / 'state')
            except daily.DailyError as exc:
                assert word in str(exc), (broken, str(exc))
            else:
                raise AssertionError(broken)
        try:
            daily.load_relay(Path(td) / 'absent.toml', Path(td) / 'state')
        except daily.DailyError as exc:
            assert 'not read' in str(exc), str(exc)
        else:
            raise AssertionError('absent file accepted')


if __name__ == '__main__':
    run_module(globals(), 'the daily file relay table')

"""The daily file's `[relay]` table: what the relay listens on, forwards to, charges and caps.

`load_relay(path, state_root)` reads a daily file (TOML) and `check_relay(table, state_root)`
checks its `[relay]` table; each raises DailyError, one ASCII line naming the key, for an
unknown key, a missing key, a wrong type or a value out of range. The table holds
`listen_port` (1024 to 65535, bound on 127.0.0.1 only), `upstream_base`, `route` (the upstream
path), `key_env` (the variable of kit's own environment that holds the provider key, never the
key itself), `test`, `usage_include`, `default_model` (one of the listed ids),
`upstream_timeout_s` (per read from the upstream), an optional `[relay.provider]` table
forwarded as the request's `provider` object, `[relay.ceilings]` with `run_usd`, `day_usd` and
`month_usd` in US dollars, and one or more `[[relay.model]]` tables, each an upstream model id
with its prices per million tokens and its `max_output_tokens`.

With `test` true the upstream is `http://127.0.0.1:PORT` only; with `test` false it is an
`https` URL, and the file is refused while the state root lies under the system's temporary
folder, where every test keeps its state root, so a daily file built in a test never reaches
the network. `key_env` must be a name the launcher's secret-name rule matches, and never
`PATH`, a name of the launcher's allow list or a name the launcher or a driver sets in a
session, so preflight's copy of kit's environment never passes the key's variable into one.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import tomllib

PORT_MIN, PORT_MAX = 1024, 65535
TIMEOUT_MAX_S = 3600
NAME_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
ROUTE_RE = re.compile(r'/[\x21-\x7e]*')
TEST_UPSTREAM_RE = re.compile(r'http://127\.0\.0\.1:([0-9]{1,5})(/[\x21-\x7e]*)?')
HTTPS_UPSTREAM_RE = re.compile(
    r'https://([A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(:[0-9]{1,5})?(/[\x21-\x7e]*)?'
)
DATA_COLLECTION = ('allow', 'deny')
RELAY_KEYS = (
    'listen_port',
    'upstream_base',
    'route',
    'key_env',
    'test',
    'usage_include',
    'default_model',
    'upstream_timeout_s',
    'ceilings',
    'model',
)
OPTIONAL_KEYS = ('provider',)
CEILING_KEYS = ('run_usd', 'day_usd', 'month_usd')
MODEL_KEYS = ('id', 'input_usd_per_mtok', 'output_usd_per_mtok', 'max_output_tokens')
PROVIDER_KEYS = ('order', 'allow_fallbacks', 'data_collection')


class DailyError(ValueError):
    """A daily file that cannot be used; the message is one ASCII line."""


@dataclass(frozen=True)
class Model:
    id: str
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    max_output_tokens: int


@dataclass(frozen=True)
class RelaySettings:
    listen_port: int
    upstream_base: str
    route: str
    key_env: str
    test: bool
    usage_include: bool
    default_model: str
    upstream_timeout_s: float
    provider: dict | None
    run_usd: float
    day_usd: float
    month_usd: float
    models: tuple[Model, ...]

    def model(self, model_id: object) -> Model | None:
        """The listed model of that id, or None."""
        return next((m for m in self.models if m.id == model_id), None)


def _ascii(value: object) -> str:
    return (
        ascii(value)
        if not isinstance(value, str)
        else value.encode('ascii', 'backslashreplace').decode('ascii')
    )


def _keys(table: object, name: str, required: tuple, optional: tuple = ()) -> dict:
    if not isinstance(table, dict):
        raise DailyError(f'{name} is not a table')
    for key in table:
        if key not in required and key not in optional:
            raise DailyError(f'{name}.{_ascii(key)} is not a known key')
    for key in required:
        if key not in table:
            raise DailyError(f'{name}.{key} is missing')
    return table


def _bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise DailyError(f'{name} is not true or false')
    return value


def _number(value: object, name: str, *, positive: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise DailyError(f'{name} is not a number')
    if value < 0 or (positive and value == 0):
        raise DailyError(
            f'{name} is {value!r}; it must be {"greater than 0" if positive else "0 or more"}'
        )
    return value


def _int(value: object, name: str, low: int, high: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DailyError(f'{name} is not an integer')
    if value < low or (high is not None and value > high):
        bound = f'{low} to {high}' if high is not None else f'{low} or more'
        raise DailyError(f'{name} is {value}; it must be {bound}')
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise DailyError(f'{name} is not a non-empty string')
    return value


def under(path: Path | str, base: Path | str) -> bool:
    """Whether `path` is `base` or lies under it, both resolved, case-folded on Windows."""

    def parts(p: Path | str) -> list[str]:
        text = os.path.realpath(str(p)).replace('\\', '/')
        text = text.casefold() if os.name == 'nt' else text
        return [x for x in text.split('/') if x]

    found, top = parts(path), parts(base)
    return bool(top) and found[: len(top)] == top


def session_names() -> frozenset[str]:
    """The names a session's environment can hold from kit, upper-cased.

    PATH and the launcher's allow list, the names the launcher passes or sets in a session
    (its terminal names, the governed home, the canary's nonce) and every name
    `launcher.build_env` gives a session of each driver.
    """
    from harness_kit import harnesses, launcher, state

    names = {'PATH', *launcher.ALLOW, *launcher.TERMINAL_NAMES, launcher.GOVERNED_HOME}
    names.add(state.CANARY_NONCE_ENV)
    folder = Path(os.path.abspath('/kit-home'))
    home = {
        'dir': str(folder),
        'endpoint': 'http://127.0.0.1:1',
        'config_file': str(folder / 'conf' / 'config'),
    }
    for name in harnesses.names():
        env, _ = launcher.build_env(
            harnesses.get(name),
            home,
            {},
            run_dir=folder / 'run',
            run_id='00000000T000000Z-000000000000',
            root=folder / 'state',
            policy_path=folder / 'policy.toml',
            workdir=folder / 'work',
            pins=lambda: dict.fromkeys(launcher.WINDOWS_PINNED, 'x'),
        )
        names.update(env)
    return frozenset(n.upper() for n in names)


def key_env_refusal(name: str) -> str | None:
    """Why `name` cannot hold the provider key, or None when it can."""
    from harness_kit.launcher import SECRET_NAME

    if not NAME_RE.fullmatch(name):
        return f'relay.key_env {_ascii(name)!s} is not a variable name'
    if not SECRET_NAME.search(name):
        return (
            f'relay.key_env {name} is not a secret name (one ending in _KEY, _TOKEN, '
            '_SECRET or _PASSWORD, or starting with GH_)'
        )
    if name.upper() in session_names():
        return f'relay.key_env {name} is a name kit run passes into or sets in a session'
    return None


def _upstream(value: object, test: bool) -> str:
    base = _text(value, 'relay.upstream_base')
    if test:
        found = TEST_UPSTREAM_RE.fullmatch(base)
        if not found or not 1 <= int(found.group(1)) <= 65535:
            raise DailyError(
                'relay.upstream_base must be http://127.0.0.1:PORT while relay.test is true'
            )
        return base
    found = HTTPS_UPSTREAM_RE.fullmatch(base)
    if not found or (found.group(2) and not 1 <= int(found.group(2)[1:]) <= 65535):
        raise DailyError('relay.upstream_base must be an https URL while relay.test is false')
    return base


def _provider(value: object) -> dict:
    table = _keys(value, 'relay.provider', (), PROVIDER_KEYS)
    order = table.get('order', [])
    if not isinstance(order, list) or not all(isinstance(x, str) and x for x in order):
        raise DailyError('relay.provider.order is not a list of non-empty strings')
    if 'allow_fallbacks' in table:
        _bool(table['allow_fallbacks'], 'relay.provider.allow_fallbacks')
    if 'data_collection' in table and table['data_collection'] not in DATA_COLLECTION:
        raise DailyError('relay.provider.data_collection is not "allow" or "deny"')
    return dict(table)


def _models(value: object) -> tuple[Model, ...]:
    if not isinstance(value, list) or not value:
        raise DailyError('relay.model is not one or more [[relay.model]] tables')
    found: list[Model] = []
    for i, item in enumerate(value):
        name = f'relay.model[{i}]'
        entry = _keys(item, name, MODEL_KEYS)
        model = Model(
            id=_text(entry['id'], f'{name}.id'),
            input_usd_per_mtok=_number(
                entry['input_usd_per_mtok'], f'{name}.input_usd_per_mtok', positive=False
            ),
            output_usd_per_mtok=_number(
                entry['output_usd_per_mtok'], f'{name}.output_usd_per_mtok', positive=False
            ),
            max_output_tokens=_int(entry['max_output_tokens'], f'{name}.max_output_tokens', 1),
        )
        if any(m.id == model.id for m in found):
            raise DailyError(f'relay.model lists the id {_ascii(model.id)} twice')
        found.append(model)
    return tuple(found)


def check_relay(table: object, state_root: Path | str) -> RelaySettings:
    """The settings of a `[relay]` table; DailyError naming the first key that is refused."""
    relay = _keys(table, 'relay', RELAY_KEYS, OPTIONAL_KEYS)
    test = _bool(relay['test'], 'relay.test')
    ceilings = _keys(relay['ceilings'], 'relay.ceilings', CEILING_KEYS)
    route = _text(relay['route'], 'relay.route')
    if not ROUTE_RE.fullmatch(route) or '?' in route or '#' in route:
        raise DailyError('relay.route is not a path starting with /, without a query')
    key_env = relay['key_env']
    if not isinstance(key_env, str):
        raise DailyError('relay.key_env is not a string')
    refusal = key_env_refusal(key_env)
    if refusal is not None:
        raise DailyError(refusal)
    models = _models(relay['model'])
    default = _text(relay['default_model'], 'relay.default_model')
    if not any(m.id == default for m in models):
        raise DailyError('relay.default_model is not one of the ids relay.model lists')
    timeout = _number(relay['upstream_timeout_s'], 'relay.upstream_timeout_s', positive=True)
    if timeout > TIMEOUT_MAX_S:
        raise DailyError(f'relay.upstream_timeout_s is over {TIMEOUT_MAX_S}')
    settings = RelaySettings(
        listen_port=_int(relay['listen_port'], 'relay.listen_port', PORT_MIN, PORT_MAX),
        upstream_base=_upstream(relay['upstream_base'], test),
        route=route,
        key_env=key_env,
        test=test,
        usage_include=_bool(relay['usage_include'], 'relay.usage_include'),
        default_model=default,
        upstream_timeout_s=timeout,
        provider=_provider(relay['provider']) if 'provider' in relay else None,
        run_usd=_number(ceilings['run_usd'], 'relay.ceilings.run_usd', positive=True),
        day_usd=_number(ceilings['day_usd'], 'relay.ceilings.day_usd', positive=True),
        month_usd=_number(ceilings['month_usd'], 'relay.ceilings.month_usd', positive=True),
        models=models,
    )
    if not test and under(state_root, tempfile.gettempdir()):
        raise DailyError(
            'relay.test is false while the state root lies under the temporary folder '
            f'{_ascii(tempfile.gettempdir())}, where tests keep theirs'
        )
    return settings


def read_daily(path: Path | str) -> dict:
    """The daily file's document; DailyError when it is not read or is not TOML."""
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise DailyError(f'daily file {_ascii(str(path))} not read: {type(exc).__name__}') from None
    try:
        return tomllib.loads(data.decode('utf-8'))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise DailyError(f'daily file is not TOML: {_ascii(str(exc))}') from None


def load_relay(path: Path | str, state_root: Path | str) -> RelaySettings:
    """The settings of the `[relay]` table of the daily file at `path`."""
    doc = read_daily(path)
    if 'relay' not in doc:
        raise DailyError('daily file has no [relay] table')
    return check_relay(doc['relay'], state_root)

"""A fake harness for the daily-home tests of `kit run`; not a test module itself.

argv: OUT VERSION CODE MODE OPTIONS HARNESS_ARGS...

`--version` prints `fake harness VERSION` and writes its environment to OUT.version-env.json.
With `KIT_CANARY_NONCE` it plays the canary of `canary_fake_harness.py` by MODE, after writing
its environment to OUT.canary-env.json and whether something listens on the port OPTIONS names
(`probe_port`) to OUT.canary-probe.json. Without it, it plays the session: it records whether
something listens on that port, sends one chat request to the endpoint in `HTTP_PROXY` (the
relay of a daily home) with the capability in `KIT_RELAY_CAPABILITY` as its bearer and the
model OPTIONS names (`model`), and writes OUT: its arguments, environment, folder, the text of
`run-open.json` in its home's folder (null when absent), whether the port listened and the
request's status. Then it exits CODE.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from canary_fake_harness import canary


def listening(port: int | None) -> bool | None:
    if not port:
        return None
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2):
            return True
    except OSError:
        return False


def ask_relay(model: str) -> int | None:
    endpoint = os.environ.get('HTTP_PROXY', '')
    body = {
        'model': model,
        'messages': [{'role': 'user', 'content': 'hello'}],
        'tools': [{'type': 'function', 'function': {'name': 'shell', 'parameters': {}}}],
    }
    request = urllib.request.Request(  # noqa: S310 - a local relay URL
        endpoint + '/v1/chat/completions',
        data=json.dumps(body).encode('ascii'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + os.environ.get('KIT_RELAY_CAPABILITY', ''),
        },
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=30) as response:
            response.read()
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return None


def write_json(path: str, value: object) -> None:
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(value, fh)


def main() -> int:
    out, version, code, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    options = json.loads(sys.argv[5])
    if sys.argv[6:] == ['--version']:
        write_json(out + '.version-env.json', dict(os.environ))
        print('fake harness ' + version)
        return 0
    port = options.get('probe_port')
    if os.environ.get('KIT_CANARY_NONCE'):
        write_json(out + '.canary-env.json', dict(os.environ))
        write_json(out + '.canary-probe.json', {'listening': listening(port)})
        canary(out, mode)
        return code
    home = Path(os.environ.get('HOME', '.')).parent
    run_open = home / 'run-open.json'
    seen = {
        'args': sys.argv[6:],
        'env': dict(os.environ),
        'cwd': os.getcwd(),
        'run_open': run_open.read_text(encoding='utf-8') if run_open.is_file() else None,
        'listening': listening(port),
        'relay_status': ask_relay(options.get('model', '')),
    }
    write_json(out, seen)
    return code


if __name__ == '__main__':
    sys.exit(main())

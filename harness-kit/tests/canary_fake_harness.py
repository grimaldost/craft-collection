"""A fake harness for the launcher and canary tests; not a test module itself.

argv: OUT VERSION CODE MODE HARNESS_ARGS...

`--version` prints `fake harness VERSION`. Without `KIT_CANARY_NONCE` in its
environment it plays the session: it starts a grandchild that writes
`KIT_RUN_ID` to `OUT.grandchild`, asks the model endpoint once (best effort),
writes its arguments, environment and folder to OUT as JSON and exits CODE.

With `KIT_CANARY_NONCE` it plays the canary's harness. It asks the endpoint in
`HTTP_PROXY` for tool calls until a text answer, then by MODE:
- `guarded`: asks the guard of the home before each call and runs the calls it
  allows (no guard loaded, as with a broken home, allows everything);
- `unguarded`: runs every call without asking;
- `nothing`: runs no call;
- `allow-only`: runs only the call whose command names an allow marker;
- `hang`: starts a grandchild that writes `OUT.late` after 4 seconds and its
  pid to `OUT.grandchild-pid`, then sleeps.
The guard of a Claude Code home is the hook its `settings.json` registers; the
guard of an opencode home is the kit CLI that the plugin folder's
`shell_config.json` names. A call is `echo WORD > FILE`, run as a file write.
Then it exits CODE.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ECHO = re.compile(r'^echo (\S+) > (\S+)$')
LATE_S = 4


def ask_endpoint(limit: int, timeout: float) -> list[str]:
    """The commands the endpoint scripts, in order, until it answers with text."""
    endpoint = os.environ.get('HTTP_PROXY', '')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    body = {'model': 'stub-model', 'max_tokens': 1, 'tools': [{'name': 'shell'}], 'messages': []}
    commands: list[str] = []
    for _ in range(limit):
        request = urllib.request.Request(  # noqa: S310 - a local stub URL
            endpoint + '/v1/messages',
            data=json.dumps(body).encode('ascii'),
            headers={'Content-Type': 'application/json', 'x-api-key': 'stub-not-a-key'},
        )
        with opener.open(request, timeout=timeout) as response:
            block = json.loads(response.read().decode('utf-8'))['content'][0]
        if block.get('type') != 'tool_use':
            break
        commands.append(block['input']['command'])
    return commands


def _claude_guard(command: str) -> bool | None:
    try:
        path = Path(os.environ['CLAUDE_CONFIG_DIR'], 'settings.json')
        hook = json.loads(path.read_text(encoding='utf-8'))['hooks']['PreToolUse'][0]['hooks'][0]
        argv = [hook['command'], *hook['args']]
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    payload = {
        'session_id': 'fake-session',
        'hook_event_name': 'PreToolUse',
        'tool_name': 'Bash',
        'tool_input': {'command': command},
        'cwd': os.getcwd(),
    }
    proc = subprocess.run(  # noqa: S603 - argv from the home, no shell
        argv, input=json.dumps(payload).encode('ascii'), capture_output=True, timeout=30
    )
    return proc.returncode == 0 and b'"deny"' not in proc.stdout


def _opencode_guard(command: str) -> bool | None:
    try:
        path = Path(os.environ['OPENCODE_CONFIG_DIR'], 'opencode.jsonc')
        folder = Path(json.loads(path.read_text(encoding='utf-8'))['plugins'][0])
        if not (folder / 'index.js').is_file():
            return None
        config = json.loads((folder / 'shell_config.json').read_text(encoding='utf-8'))
        argv = config['cli_argv']
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
    observed = dict.fromkeys(('parent', 'root', 'origin'), 'unavailable')
    event = {
        'kit_event': 1,
        'run_id': os.environ.get('KIT_RUN_ID') or None,
        'harness': {'name': 'opencode', 'version': config['harness_version']},
        'session': {'id': 'fake-session', 'parent_id': None, 'root_id': None},
        'origin': 'unknown',
        'observation': {
            'session': 'observed',
            **observed,
            'command': 'observed',
            'paths': 'not_applicable',
        },
        'act': {
            'kind': 'shell',
            'command': command,
            'argv': None,
            'paths': [],
            'cwd': os.getcwd(),
            'payload_sha256': hashlib.sha256(command.encode('utf-8')).hexdigest(),
        },
    }
    proc = subprocess.run(  # noqa: S603 - argv from the home, no shell
        argv, input=json.dumps(event).encode('ascii'), capture_output=True, timeout=30
    )
    try:
        return json.loads(proc.stdout.decode('utf-8'))['effect'] == 'allow'
    except (ValueError, KeyError, TypeError):
        return False


def guard_allows(command: str) -> bool:
    found = _claude_guard if 'CLAUDE_CONFIG_DIR' in os.environ else _opencode_guard
    return found(command) is not False


def run_call(command: str) -> None:
    match = ECHO.match(command)
    if match:
        Path(match.group(2)).write_text(match.group(1) + '\n', encoding='ascii')


def canary(out: str, mode: str) -> None:
    if mode == 'hang':
        late = (
            'import sys, time; time.sleep(float(sys.argv[2])); open(sys.argv[1], "w").write("late")'
        )
        child = subprocess.Popen([sys.executable, '-c', late, out + '.late', str(LATE_S)])  # noqa: S603
        Path(out + '.grandchild-pid').write_text(str(child.pid), encoding='ascii')
        time.sleep(3600)
    for command in ask_endpoint(5, 10):
        if mode == 'nothing':
            continue
        if mode == 'allow-only' and 'allow-' not in command:
            continue
        if mode == 'guarded' and not guard_allows(command):
            continue
        run_call(command)


def session(out: str) -> None:
    probe = 'import os, sys; open(sys.argv[1], "w").write(os.environ.get("KIT_RUN_ID", "none"))'
    subprocess.run([sys.executable, '-c', probe, out + '.grandchild'], check=True)  # noqa: S603
    try:
        ask_endpoint(1, 2)
    except (OSError, ValueError, KeyError, IndexError):
        pass
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({'args': sys.argv[5:], 'env': dict(os.environ), 'cwd': os.getcwd()}, fh)


def main() -> int:
    out, version, code, mode = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
    if sys.argv[5:] == ['--version']:
        print('fake harness ' + version)
        return 0
    if os.environ.get('KIT_CANARY_NONCE'):
        canary(out, mode)
    else:
        session(out)
    return code


if __name__ == '__main__':
    sys.exit(main())

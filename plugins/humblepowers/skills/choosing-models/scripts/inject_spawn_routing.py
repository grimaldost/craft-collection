#!/usr/bin/env python3
"""PreToolUse hook: name the routing decision at the moment a spawn takes it.

`choosing-models` governs one moment - the moment a (model, effort) pair is
chosen for someone else's run - and had no trigger there. Measured: ZERO
invocations across a 40-hour, 139-subagent programme, against a written owner
order transcribed verbatim three times and repeated in the anchor's every cursor
block, with 65% of output and 81% of uncached input left at the top tier. Twenty
subagents at the frontier tier in one day ($14.48, ten of them mechanical
rewriters); 23 more the next, killed by the owner mid-run. Prose has now failed
against the strongest instruction channel there is, so this is the rung below it.

It scales with a fan-out, which is the reason it is a hook and not a sentence: a
54-item batch is reminded ONCE, at the script, instead of once per agent or not
at all.

  --pre-tool-use   Matched on the spawn surface (`Agent`; `Workflow` where the
                   harness has one). Injects a short advisory block naming the
                   activation test and the batch counter-rule. Ships ON;
                   HUMBLEPOWERS_SPAWN_ROUTING_HINT=0 is the opt-out.

Three silences keep it from becoming the noise that gets hooks switched off:

  - a spawn that already carries `model` has been routed. The field is present
    in `tool_input` only when the caller passed one, so its presence IS the
    evidence that a decision was taken rather than inherited. `Workflow` has no
    top-level `model`: routing lives in the script, per `agent()` call, so the
    script (inline `script`, or the file at `scriptPath`) is read and the hint
    stays silent only when every `agent()` call names a model. A script it
    cannot read, a call whose options it cannot resolve, and a script that runs
    another workflow all keep the hint - unsure must not become silent;
  - at most one hint per session per HINT_COOLDOWN_S;
  - anything that is not a spawn surface.

It is ADVISORY: the payload is `additionalContext` with no `permissionDecision`,
which is the documented way to add context from PreToolUse without voting on the
allow/deny outcome. `allow` would skip a permission prompt the operator
configured, and `deny` would block real work over a reminder; neither is this
hook's business. One consequence to know: context added during a turn reaches the
model's NEXT turn, so the hint does not stop the spawn that triggered it - it
stands in front of the rest of the batch and the rest of the run, which is where
the measured loss actually accumulated.

The block names the activation test and points at the skill; it does NOT restate
the tier thresholds. `models.toml` owns those, and a second copy inside a hook is
exactly the drift this corpus already pays for elsewhere.

Contract, inherited from `choosing-tools/scripts/inject_dispatch.py`: stdlib
only, no subprocesses, no network, ASCII-only output (hook stdout encoding
follows the host console), and every path returns 0 - a PreToolUse hook that
errors or hangs costs the tool call it was meant to annotate.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

GATE = 'HUMBLEPOWERS_SPAWN_ROUTING_HINT'
STATE_DIR_ENV = 'HUMBLEPOWERS_SPAWN_HINT_STATE_DIR'
STATE_NAME = 'spawn-hint.json'
# Tool names that spawn someone else's run. `Agent` is the spawner (renamed from
# `Task` in CC 2.1.63; the TaskCreate/TaskGet family is the separate todo system
# and must never match here). `Workflow` is carried because the skill's emission
# surfaces name `workflow agent()` as a routed surface; where no such tool
# exists the entry simply never matches.
SPAWN_TOOLS = ('Agent', 'Workflow')
HINT_COOLDOWN_S = 600  # one reminder per session per 10 minutes
MAX_TRACKED_SESSIONS = 50  # the state file is a cooldown, not a history
MAX_SCRIPT_BYTES = 2_000_000  # a workflow script larger than this is not parsed
MAX_RESOLVE_DEPTH = 4  # const / spread hops followed to find shared options

AGENT_LEAD = (
    'This spawn names no model, so the agent inherits this session tier: a '
    "(model, effort) pair is being set for someone else's run by default "
    'rather than by decision.'
)
WORKFLOW_COUNT_LEAD = (
    '{unrouted} of {total} agent() calls in this workflow script name no model '
    'this hook can see, so those agents inherit this session tier: a (model, '
    "effort) pair is being set for someone else's run by default rather than by "
    'decision.'
)
WORKFLOW_UNKNOWN_LEAD = (
    'This workflow script could not be read here, or it runs another workflow, '
    'so whether each agent() call names a model is unknown; an agent() call '
    'with no model inherits this session tier.'
)
HINT_BODY = (
    'Activation test: is a (model, effort) pair about to be chosen for someone '
    "else's run? If yes, score it with the humblepowers:choosing-models rubric "
    'and pass an explicit model - that skill and its models.toml own the '
    'thresholds, which this hook deliberately does not restate.\n'
    'Two or more agents dispatched in one decision are a batch, and the '
    'single-task exception does not apply to a batch.\n'
    f'(Once per session per {HINT_COOLDOWN_S // 60} min; {GATE}=0 silences it.)'
)
HINT = AGENT_LEAD + '\n' + HINT_BODY


def _ascii(text: str) -> str:
    """Collapse to ASCII for output; hook stdout may be a codepage-limited console."""
    return text.encode('ascii', 'replace').decode('ascii')


def _state_path() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    base = override or os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / ('' if override else 'humblepowers-spawn-routing') / STATE_NAME


def is_spawn(tool_name: str) -> bool:
    return tool_name in SPAWN_TOOLS


class _UnparsedError(ValueError):
    """The script is not balanced the way this scanner reads it."""


def _mask(src: str) -> str:
    """`src` with comment text and string/template contents blanked, offsets and
    newlines kept, so brackets and names can be matched on code alone. The code
    inside a template's `${...}` stays visible. Raises _UnparsedError on an
    unterminated literal. A `/` opens a regex literal where an operand is
    expected (after an operator, an opening bracket, or a keyword such as
    `return`); a misread there fails the parse, which fails toward the hint."""
    out = list(src)
    n = len(src)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] not in '\r\n':
                out[k] = ' '

    def literal_end(i: int, close: str) -> int:
        # Index of the unescaped `close` that ends a literal whose body starts
        # at `i`; inside a regex, a `[...]` class may hold an unescaped `/`.
        in_class = False
        while i < n:
            ch = src[i]
            if ch == '\\':
                i += 2
                continue
            if ch == '\n':
                raise _UnparsedError
            if close == '/' and in_class:
                in_class = ch != ']'
            elif close == '/' and ch == '[':
                in_class = True
            elif ch == close:
                return i
            i += 1
        raise _UnparsedError

    def regex_can_start(i: int) -> bool:
        k = i - 1
        while k >= 0 and out[k].isspace():
            k -= 1
        if k < 0 or out[k] in _OPERAND_EXPECTED:
            return True
        word = _TRAILING_WORD.search(''.join(out[max(0, k - 9) : k + 1]))
        return bool(word) and word.group(0) in _REGEX_KEYWORDS

    def code(i: int, in_expr: bool) -> int:
        depth = 0
        while i < n:
            c = src[i]
            if src.startswith('//', i):
                j = src.find('\n', i)
                j = n if j < 0 else j
                blank(i, j)
                i = j
            elif src.startswith('/*', i):
                j = src.find('*/', i + 2)
                if j < 0:
                    raise _UnparsedError
                blank(i, j + 2)
                i = j + 2
            elif c in '\'"' or (c == '/' and regex_can_start(i)):
                j = literal_end(i + 1, c)
                blank(i + 1, j)
                i = j + 1
            elif c == '`':
                i = template(i + 1)
            elif in_expr and c == '{':
                depth += 1
                i += 1
            elif in_expr and c == '}':
                if depth == 0:
                    return i
                depth -= 1
                i += 1
            else:
                i += 1
        if in_expr:
            raise _UnparsedError
        return i

    def template(i: int) -> int:
        while i < n:
            if src[i] == '\\':
                blank(i, i + 2)
                i += 2
            elif src[i] == '`':
                return i + 1
            elif src.startswith('${', i):
                blank(i, i + 2)
                j = code(i + 2, True)
                blank(j, j + 1)
                i = j + 1
            else:
                blank(i, i + 1)
                i += 1
        raise _UnparsedError

    code(0, False)
    return ''.join(out)


_OPERAND_EXPECTED = frozenset('(,=:[!&|?{};+-*%<>~^')
_TRAILING_WORD = re.compile(r'[A-Za-z_$][\w$]*$')
_REGEX_KEYWORDS = frozenset(
    {'return', 'typeof', 'case', 'in', 'of', 'void', 'delete', 'throw', 'yield', 'await'}
)
_OPEN = {'(': ')', '[': ']', '{': '}'}
_CLOSE = frozenset(')]}')
_AGENT_CALL = re.compile(r'(?<![\w$.])agent\s*\(')
_NESTED_WORKFLOW = re.compile(r'(?<![\w$.])workflow\s*\(')
_FUNCTION_NAME = re.compile(r'function\s*\*?\s*$')
_IDENT = re.compile(r'[A-Za-z_$][\w$]*')
# The head of a call to a plain identifier: `route(`, `R(`. A member path
# (`routes.of(`) is left out on purpose - its body is not a definition in the script.
_CALL_HEAD = re.compile(r'([A-Za-z_$][\w$]*)\s*\(')
_RETURN_OBJECT = re.compile(r'(?<![\w$.])return\s*\(?\s*\{')
_KEY = re.compile(r'\s*(?:([\'"])([^\'"]*)\1|([A-Za-z_$][\w$]*))\s*(:?)')
_NO_VALUE = frozenset({'undefined', 'null', "''", '""', '``'})


def _split_top(mask: str, start: int) -> tuple[list[tuple[int, int]], int]:
    """Top-level comma-separated spans inside the bracket opening at `start`,
    and the index of its closing bracket. Raises _UnparsedError when unbalanced."""
    stack = [_OPEN[mask[start]]]
    spans: list[tuple[int, int]] = []
    begin = start + 1
    for i in range(begin, len(mask)):
        c = mask[i]
        if c in _OPEN:
            stack.append(_OPEN[c])
        elif c in _CLOSE:
            if c != stack.pop():
                raise _UnparsedError
            if not stack:
                spans.append((begin, i))
                return [(a, b) for a, b in spans if mask[a:b].strip()], i
        elif c == ',' and len(stack) == 1:
            spans.append((begin, i))
            begin = i + 1
    raise _UnparsedError


def _const_object(name: str, mask: str) -> tuple[int, int] | None:
    """The span of the object literal a `const|let|var NAME = {...}` binds."""
    pattern = rf'(?<![\w$.])(?:const|let|var)\s+{re.escape(name)}\s*=\s*\{{'
    m = re.search(pattern, mask)
    if not m:
        return None
    _, close = _split_top(mask, m.end() - 1)
    return m.end() - 1, close + 1


def _function_object(name: str, mask: str) -> tuple[int, int] | None:
    """The span of the object literal the function NAME returns, when the script
    defines it as `const NAME = (...) => ({...})`, as an arrow with a block body, or
    as `function NAME(...) {...}` - the first object a `return` hands back. None when
    NAME is not defined in the script or returns nothing the hook can read."""
    arrow = re.search(
        rf'(?<![\w$.])(?:const|let|var)\s+{re.escape(name)}\s*=\s*(?:async\s*)?'
        r'(?:\([^()]*\)|[A-Za-z_$][\w$]*)\s*=>\s*',
        mask,
    )
    if arrow:
        rest = mask[arrow.end() :]
        body = rest.lstrip()
        at = arrow.end() + len(rest) - len(body)
        if body.startswith('('):
            inner = mask[at + 1 :].lstrip()
            if inner.startswith('{'):
                start = at + 1 + len(mask[at + 1 :]) - len(inner)
                _, close = _split_top(mask, start)
                return start, close + 1
            return None
        if body.startswith('{'):
            _, close = _split_top(mask, at)
            return _returned_object((at, close + 1), mask)
        return None
    fn = re.search(rf'(?<![\w$.])function\s+{re.escape(name)}\s*\([^()]*\)\s*\{{', mask)
    if fn:
        _, close = _split_top(mask, fn.end() - 1)
        return _returned_object((fn.end() - 1, close + 1), mask)
    return None


def _returned_object(block: tuple[int, int], mask: str) -> tuple[int, int] | None:
    """The first object literal a `return` inside `block` hands back."""
    m = _RETURN_OBJECT.search(mask, block[0], block[1])
    if not m:
        return None
    _, close = _split_top(mask, m.end() - 1)
    return m.end() - 1, close + 1


def _names_model(span: tuple[int, int], src: str, mask: str, depth: int = 0) -> bool:
    """Whether the expression at `span` is an options object with a top-level
    `model` key - directly, as shorthand, or through a spread or a const. Only
    the top level counts: a schema property named `model` routes nothing."""
    if depth > MAX_RESOLVE_DEPTH:
        return False
    a, b = span
    text = mask[a:b].strip()
    if _IDENT.fullmatch(text):
        bound = _const_object(text, mask)
        return bound is not None and _names_model(bound, src, mask, depth + 1)
    if not (text.startswith('{') and text.endswith('}')):
        return False
    props, _ = _split_top(mask, a + mask[a:b].index('{'))
    # A later key wins in an object literal, so the answer is the LAST word on
    # `model`: `{ ...routed, model: undefined }` names none.
    routed = False
    for pa, pb in props:
        if mask[pa:pb].strip().startswith('...'):
            inner = pa + mask[pa:pb].index('...') + 3
            # A spread of a CALL - `{ ...route(id) }` - is the shape a scored batch
            # emits. It counts only when the callee is defined in this script and is
            # seen to return an object that names a model; a helper the hook cannot
            # read, or one that sets no model, keeps the hint (T93b).
            if _spread_call_routes((inner, pb), src, mask, depth) or _names_model(
                (inner, pb), src, mask, depth + 1
            ):
                routed = True
            continue
        m = _KEY.match(src, pa, pb)
        if not m or (m.group(2) or m.group(3)) != 'model':
            continue
        # shorthand `{ model }` routes; `model: <value>` routes unless the value is empty
        routed = not m.group(4) or src[m.end() : pb].strip() not in _NO_VALUE
    return routed


def _spread_call_routes(span: tuple[int, int], src: str, mask: str, depth: int) -> bool:
    """Whether the spread operand at `span` is ONE call to a function defined in the
    script whose returned object names a model."""
    a, b = span
    lead = len(mask[a:b]) - len(mask[a:b].lstrip())
    head = _CALL_HEAD.match(mask, a + lead, b)
    if not head:
        return False
    _, close = _split_top(mask, head.end() - 1)
    if mask[close + 1 : b].strip():
        return False  # not a single call: `f(x) ? {} : g(x)`, `f(x).y`, ...
    body = _function_object(head.group(1), mask)
    return body is not None and _names_model(body, src, mask, depth + 1)


def workflow_routing(script: str) -> tuple[int, int] | None:
    """(unrouted, total) over the script's `agent()` calls, or None when the
    answer is unknowable here: an unparseable script, no `agent()` call found,
    or a nested `workflow()` whose agents live in another script."""
    try:
        mask = _mask(script)
        if _NESTED_WORKFLOW.search(mask):
            return None
        total = unrouted = 0
        for m in _AGENT_CALL.finditer(mask):
            if _FUNCTION_NAME.search(mask[max(0, m.start() - 20) : m.start()]):
                continue  # a definition named agent, not a call
            args, _ = _split_top(mask, m.end() - 1)
            total += 1
            if not any(_names_model(arg, script, mask) for arg in args):
                unrouted += 1
    except (_UnparsedError, IndexError, ValueError):
        return None
    return (unrouted, total) if total else None


def _workflow_script(tool_input: dict, cwd: str) -> str | None:
    script = tool_input.get('script')
    if isinstance(script, str) and script.strip():
        return script
    script_path = tool_input.get('scriptPath')
    if not isinstance(script_path, str) or not script_path:
        return None  # e.g. a saved workflow launched by name
    path = Path(script_path)
    if not path.is_absolute() and cwd:
        path = Path(cwd) / path
    try:
        if path.stat().st_size > MAX_SCRIPT_BYTES:
            return None
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


def hint_lead(tool_name: str, tool_input: dict, cwd: str = '') -> str | None:
    """The hint's opening line when this call is a spawn that has NOT been
    routed, else None. On `Agent`, `model` absent means the subagent's model is
    resolved later from its frontmatter, an env var, or the parent conversation -
    none of which is a decision taken here. On `Workflow` the decision is taken
    per `agent()` call inside the script."""
    if not is_spawn(tool_name):
        return None
    if tool_name != 'Workflow':
        return None if tool_input.get('model') else AGENT_LEAD
    script = _workflow_script(tool_input, cwd)
    routing = workflow_routing(script) if script is not None else None
    if routing is None:
        return WORKFLOW_UNKNOWN_LEAD
    unrouted, total = routing
    if not unrouted:
        return None
    return WORKFLOW_COUNT_LEAD.format(unrouted=unrouted, total=total)


def needs_hint(tool_name: str, tool_input: dict, cwd: str = '') -> bool:
    """True when this call is a spawn that has NOT been routed."""
    return hint_lead(tool_name, tool_input, cwd) is not None


def due(last_ts: float, now: float, cooldown_s: int = HINT_COOLDOWN_S) -> bool:
    """Whether the cooldown has elapsed. Pure, so the window is testable without
    sleeping through it."""
    return now - last_ts >= cooldown_s


def _read_state(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path: Path, state: dict) -> None:
    # Best-effort by contract: an unwritable state dir must cost the reminder
    # nothing. It fails toward reminding again, never toward silence.
    with contextlib.suppress(Exception):
        if len(state) > MAX_TRACKED_SESSIONS:
            newest = sorted(state.items(), key=lambda kv: kv[1], reverse=True)
            state = dict(newest[:MAX_TRACKED_SESSIONS])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding='utf-8')


def _pre_tool_use() -> int:
    if os.environ.get(GATE) == '0':
        return 0
    try:
        payload = json.loads(sys.stdin.buffer.read().decode('utf-8-sig'))
    except (ValueError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    tool_name = payload.get('tool_name')
    tool_name = tool_name if isinstance(tool_name, str) else ''
    tool_input = payload.get('tool_input')
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    cwd = payload.get('cwd')
    lead = hint_lead(tool_name, tool_input, cwd if isinstance(cwd, str) else '')
    if lead is None:
        return 0

    session = payload.get('session_id')
    session = session if isinstance(session, str) and session else 'unknown'
    path = _state_path()
    state = _read_state(path)
    last = state.get(session)
    now = time.time()
    if isinstance(last, (int, float)) and not due(float(last), now):
        return 0

    # Emit FIRST - the injection is the hook's entire purpose - then record.
    print(
        json.dumps(
            {
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'additionalContext': _ascii(lead + '\n' + HINT_BODY),
                }
            }
        )
    )
    state[session] = now
    _write_state(path, state)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Spawn-time model-routing hint (PreToolUse).')
    parser.add_argument('--pre-tool-use', action='store_true', help='PreToolUse entry point')
    args = parser.parse_args(argv)
    try:
        if args.pre_tool_use:
            return _pre_tool_use()
        parser.print_help()
        return 0
    except Exception:
        return 0  # fail open: a hook error must never cost the tool call


if __name__ == '__main__':
    sys.exit(main())

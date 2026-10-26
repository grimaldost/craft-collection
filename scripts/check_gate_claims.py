"""Fail when a plugin's prose claims an env-gate default the gate does not have.

Every hook in this collection is controlled by one environment variable, and the
default of that control is readable from the guard itself: a hook that returns
early on `== '0'` ships ON and `=0` is its opt-out; one that proceeds only on
`== '1'` ships OFF and `=1` is its opt-in. A three-valued gate (`0`, `observe`,
`on`) is classified by its unset value -- the `get()` default, else the value the
guard falls through to -- never by whether `observe` appears in it: a gate whose
unset value is `observe` ships in observe mode (it records and prints nothing),
while one with `'0'` off, `'observe'` logging and an unset on still ships on. The
fall-through is the guard function's closing `return 'on' | 'off' | 'observe'` when
it has one, else the one mode the compared values leave unnamed (`'0'` and `'on'`
compared: unset is observe), else the two-valued reading above. The documentation
is the copy that
drifts, and it drifted silently for a full release: `compaction-survival`'s body
and its cold-start recipe both described the re-injection hook as "off by
default, with SESSION_WORKFLOW_ANCHOR_HOOKS=1" for three weeks after 0.21.0
shipped it ON, while `hooks.json`, the script docstring, the tests, the README
and the CHANGELOG all said the opposite. A reader who believes a mechanism is
inert does not reason about what it does -- which is the whole failure the
default-on change existed to fix, reintroduced one layer up.

Nothing checked it, so this does. The source of truth is the guard expression;
prose is compared against it.

What counts as a claim, and what deliberately does not:
- Prose only. Fenced code blocks are literal commands -- `SESSION_WORKFLOW_ANCHOR_HOOKS=1
  python anchor_inject.py` is a person setting a variable to simulate a hook, not
  a claim about its default, and a verification recipe that could not say that
  would be worse than no check.
- `CHANGELOG.md` is exempt everywhere. It is a dated record of what was true at a
  release, and rewriting history to match the present is the opposite of the
  point.
- Paragraph scope, not line scope. Markdown wraps, and the observed defect had
  "off by default" and the gate name on different lines of one bullet. A table
  row is its own unit: a Hooks table lists gates with different defaults, and a
  row is one claim.

One structural claim rides along: the root README's Hooks table lists one row per
hook entry point in the plugins' `hooks.json` files. The table had three rows for
nine entry points (and called the opt-in verification gate "on or not shipped")
because nothing compared the two counts. The check counts `command` hooks and
table body rows; it does not read the cell text.

Usage: `python scripts/check_gate_claims.py [repo_root]`. Exit 1 on findings.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

# A gate is a switch only when it is compared against one of these values. An env
# var read for a path or a truthy presence check is a value, not a gate, and is
# deliberately out of scope.
MODE_OF = {'0': 'off', 'off': 'off', '1': 'on', 'on': 'on', 'observe': 'observe'}
CONTROL_VALUES = ('0', '1')
# What gates_in_source reports per default: the value a reader is told to set
# (the opt-out of an on gate, the opt-in of an off gate), or 'observe'.
CONTROL_OF = {'on': '0', 'off': '1', 'observe': 'observe'}
EXEMPT_MD = {'CHANGELOG.md'}
FENCE = re.compile(r'^\s*```')
ON_PHRASE = re.compile(r'\bon by default\b|\bships on\b|\benabled by default\b', re.I)
OFF_PHRASE = re.compile(
    r'\boff by default\b|\bships off\b|\bdisabled by default\b|\bopt in\b', re.I
)
OBSERVE_PHRASE = re.compile(
    r'\bobserve(?:s|d)? (?:mode )?by default\b|\bin observe mode by default\b'
    r'|\bships in observe\b',
    re.I,
)
NOT_OBSERVE_PHRASE = re.compile(
    r'\bon by default\b|\bships on\b|\benabled by default\b|\boff by default\b'
    r'|\bships off\b|\bdisabled by default\b',
    re.I,
)
_UNWRAP = ('strip', 'lower', 'casefold')
LIST_ITEM = re.compile(r'^\s*(?:[-*+]|\d+[.)])\s+')


def module_constants(tree: ast.Module) -> dict[str, str]:
    """Module-level `NAME = 'literal'` bindings, so a guard written against a
    constant (`ENV_GATE`, `NUDGE_GATE`) resolves to the variable it names."""
    out: dict[str, str] = {}
    for node in tree.body:
        is_str_const = isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
        if is_str_const and isinstance(node.value.value, str):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value.value
    return out


def _env_read_name(node: ast.AST, consts: dict[str, str]) -> str | None:
    """The env var name in `os.environ.get(X)` / `os.getenv(X)`, else None."""
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    owner = node.func.value
    is_environ_get = node.func.attr == 'get' and (
        (isinstance(owner, ast.Attribute) and owner.attr == 'environ')
        or (isinstance(owner, ast.Name) and owner.id == 'environ')
    )
    is_getenv = node.func.attr == 'getenv' and isinstance(owner, ast.Name) and owner.id == 'os'
    if not (is_environ_get or is_getenv) or not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name):
        return consts.get(arg.id)
    return None


def _str_const(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _env_read(node: ast.AST, consts: dict[str, str]) -> tuple[str, str | None] | None:
    """(gate name, default) for an env read, through `.strip()`/`.lower()` and `or 'x'`."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or) and len(node.values) == 2:
        inner = _env_read(node.values[0], consts)
        fallback = _str_const(node.values[1])
        if inner is not None and inner[1] is None and fallback is not None:
            return inner[0], fallback
        return inner
    while (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _UNWRAP
        and not node.args
    ):
        node = node.func.value
    name = _env_read_name(node, consts)
    if name is None or not isinstance(node, ast.Call):
        return None
    default = _str_const(node.args[1]) if len(node.args) >= 2 else None
    return name, default


def _scope_nodes(scope: ast.AST):
    """Every node of one scope, not descending into nested functions or classes."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


def _compared_values(node: ast.AST) -> list[str]:
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return [v for v in (_str_const(e) for e in node.elts) if v is not None]
    value = _str_const(node)
    return [] if value is None else [value]


def _tail_mode(scope: ast.AST) -> str | None:
    """The mode a guard function falls through to: its closing `return 'on'|'off'|'observe'`."""
    if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)) or not scope.body:
        return None
    last = scope.body[-1]
    value = _str_const(last.value) if isinstance(last, ast.Return) else None
    return value if value in ('on', 'off', 'observe') else None


def _unset_mode(default: str | None, compared: set[str], tail: str | None) -> str:
    """on | off | observe: what the gate does when the variable is unset."""
    if default in MODE_OF:
        return MODE_OF[default]
    if tail is not None:
        return tail
    named = {MODE_OF[v] for v in compared if v in MODE_OF}
    remaining = {'on', 'off', 'observe'} - named
    if len(remaining) == 1:
        return remaining.pop()
    if 'off' in named:
        return 'on'
    if 'on' in named:
        return 'off'
    return 'on'


def _bindings(nodes: list[ast.AST], consts: dict[str, str]) -> dict[str, tuple[str, str | None]]:
    """Local names bound to an env read in one scope: `value = os.environ.get(X, 'd')`."""
    bound: dict[str, tuple[str, str | None]] = {}
    for node in nodes:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        else:
            continue
        read = _env_read(value, consts)
        if read is not None and isinstance(target, ast.Name):
            bound[target.id] = read
    return bound


def classify_gates(text: str) -> dict[str, str]:
    """{gate name: 'on' | 'off' | 'observe'}: each gate's default, read from its guard."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    consts = module_constants(tree)
    scopes = [tree] + [
        n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    found: dict[str, str] = {}
    for scope in scopes:
        nodes = list(_scope_nodes(scope))
        bound = _bindings(nodes, consts)
        compared: dict[str, set[str]] = {}
        defaults: dict[str, str | None] = {}
        for node in nodes:
            if not isinstance(node, ast.Compare) or len(node.ops) != 1:
                continue
            if not isinstance(node.ops[0], (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                continue
            left = node.left
            read = bound.get(left.id) if isinstance(left, ast.Name) else _env_read(left, consts)
            if read is None:
                continue
            name, default = read
            compared.setdefault(name, set()).update(_compared_values(node.comparators[0]))
            if defaults.get(name) is None:
                defaults[name] = default
        tail = _tail_mode(scope)
        for name, values in compared.items():
            if values & set(MODE_OF):
                found[name] = _unset_mode(defaults.get(name), values, tail)
    return found


def gates_in_source(text: str) -> dict[str, str]:
    """{gate name: control value} for one module.

    The control value is the one a reader is told to SET -- the opt-out of an
    on-by-default gate, the opt-in of an off-by-default one -- or `'observe'` for
    a gate that ships in observe mode (documented with `=on` and `=0`).
    `get(X) == '0'` guards an early return, so '0' turns it off and the gate
    ships on; `== '1'` guards the proceed path, so '1' turns it on and the gate
    ships off. `!=` is the same statement inverted. A three-valued gate is read
    by its unset value (see the module docstring)."""
    return {name: CONTROL_OF[mode] for name, mode in classify_gates(text).items()}


def collect_gates(root: Path) -> tuple[dict[str, str], list[str]]:
    """Every boolean env gate the plugins ship, plus any that cannot be
    classified because two modules guard it with opposite polarity. An
    unclassifiable gate is reported, never silently skipped: a check that goes
    quiet when it is confused is the failure mode this repo keeps a registry to
    prevent."""
    gates: dict[str, str] = {}
    conflicts: list[str] = []
    for py in sorted((root / 'plugins').rglob('*.py')):
        if py.name.startswith('test_') or '__pycache__' in py.parts:
            continue
        for name, control in gates_in_source(py.read_text(encoding='utf-8')).items():
            if name in gates and gates[name] != control:
                conflicts.append(
                    f'{name}: guarded as both opt-out and opt-in across modules; '
                    'no single documented default can be correct'
                )
            gates[name] = control
    return gates, conflicts


def prose_paragraphs(text: str) -> list[tuple[int, str]]:
    """(1-based start line, paragraph) for the prose of a markdown file, with
    fenced code removed."""
    paragraphs: list[tuple[int, str]] = []
    buf: list[str] = []
    start = 1
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.lstrip().startswith('|'):
            if buf:
                paragraphs.append((start, '\n'.join(buf)))
                buf = []
            paragraphs.append((lineno, line))
            continue
        if line.strip():
            if buf and LIST_ITEM.match(line):
                paragraphs.append((start, '\n'.join(buf)))
                buf = []
            if not buf:
                start = lineno
            buf.append(line)
        elif buf:
            paragraphs.append((start, '\n'.join(buf)))
            buf = []
    if buf:
        paragraphs.append((start, '\n'.join(buf)))
    return paragraphs


def _check_observe_gate(para: str, gate: str, rel: str, start: int) -> list[str]:
    """An observe-default gate takes `=on` and `=0`; prose calling it on or off by default is stale."""
    findings = []
    for match in re.finditer(rf'{re.escape(gate)}\s*=\s*[\'"`]?(\d)', para):
        if match.group(1) == '1':
            findings.append(
                f'{rel}:{start}: {gate}=1 but the gate ships in observe mode; '
                f'its controls are {gate}=on (advice) and {gate}=0 (off)'
            )
    if NOT_OBSERVE_PHRASE.search(para):
        findings.append(
            f'{rel}:{start}: paragraph mentions {gate} and describes another default; '
            'the gate ships in observe mode (observe by default)'
        )
    return findings


def check_markdown(path: Path, gates: dict[str, str], rel: str) -> list[str]:
    findings = []
    text = path.read_text(encoding='utf-8')
    for start, para in prose_paragraphs(text):
        for gate, control in sorted(gates.items()):
            if gate not in para:
                continue
            if control == 'observe':
                findings.extend(_check_observe_gate(para, gate, rel, start))
                continue
            wrong = '1' if control == '0' else '0'
            ships = 'on' if control == '0' else 'off'
            for match in re.finditer(rf'{re.escape(gate)}\s*=\s*[\'"`]?(\d)', para):
                if match.group(1) == wrong:
                    findings.append(
                        f'{rel}:{start}: {gate}={wrong} but the gate ships {ships}; '
                        f'the documented control is {gate}={control}'
                    )
            contradiction = OFF_PHRASE if control == '0' else ON_PHRASE
            if contradiction.search(para) or OBSERVE_PHRASE.search(para):
                findings.append(
                    f'{rel}:{start}: paragraph mentions {gate} and describes the '
                    f'opposite default; the gate ships {ships}'
                )
    return findings


def hook_entry_points(root: Path) -> int:
    """Number of `command` hooks across every plugin's hooks/hooks.json."""
    count = 0
    for manifest in sorted((root / 'plugins').glob('*/hooks/hooks.json')):
        try:
            events = json.loads(manifest.read_text(encoding='utf-8')).get('hooks', {})
        except (OSError, ValueError, AttributeError):
            continue
        for groups in events.values() if isinstance(events, dict) else []:
            for group in groups if isinstance(groups, list) else []:
                for hook in group.get('hooks', []) if isinstance(group, dict) else []:
                    if isinstance(hook, dict) and hook.get('type') == 'command':
                        count += 1
    return count


def hooks_table_rows(readme: str) -> int | None:
    """Body rows of the first table under the README's `## Hooks` heading, or
    None when the section has no table."""
    rows: list[str] = []
    in_section = False
    for line in readme.splitlines():
        if line.startswith('## '):
            if in_section:
                break
            in_section = line.strip() == '## Hooks'
            continue
        if not in_section:
            continue
        if line.startswith('|'):
            rows.append(line)
        elif rows:
            break
    if not rows:
        return None
    return max(len(rows) - 2, 0)  # header and separator are not hooks


def check_hooks_table(root: Path) -> list[str]:
    readme = root / 'README.md'
    if not readme.is_file():
        return []
    entry_points = hook_entry_points(root)
    rows = hooks_table_rows(readme.read_text(encoding='utf-8'))
    if rows is None:
        return ['README.md: no table under "## Hooks"; one row per hook entry point is expected']
    if rows != entry_points:
        return [
            f'README.md: Hooks table has {rows} row(s) but the plugins ship '
            f'{entry_points} hook entry point(s) in hooks.json; one row per hook'
        ]
    return []


def run(root: Path) -> list[str]:
    gates, findings = collect_gates(root)
    if not gates:
        return [*findings, 'no env gates found under plugins/; the scan resolved nothing']
    targets = sorted((root / 'plugins').rglob('*.md')) + sorted(root.glob('*.md'))
    for md in targets:
        if md.name in EXEMPT_MD or '__pycache__' in md.parts:
            continue
        findings.extend(check_markdown(md, gates, md.relative_to(root).as_posix()))
    findings.extend(check_hooks_table(root))
    return findings


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] in (['-h'], ['--help']):
        print(__doc__.strip())
        return 0
    root = Path(argv[0]) if argv else Path(__file__).resolve().parent.parent
    findings = run(root)
    for finding in findings:
        print(f'  {finding}')
    if findings:
        print(f'FAIL: {len(findings)} gate-claim finding(s)')
        return 1
    print('ok: every documented env-gate default matches its guard')
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Fail when a plugin's prose claims an env-gate default the gate does not have.

Every hook in this collection is controlled by one environment variable, and the
polarity of that control is readable from the guard itself: a hook that returns
early on `== '0'` ships ON and `=0` is its opt-out; one that proceeds only on
`== '1'` ships OFF and `=1` is its opt-in. The documentation is the copy that
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
  "off by default" and the gate name on different lines of one bullet.

Usage: `python scripts/check_gate_claims.py [repo_root]`. Exit 1 on findings.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# A gate is a boolean switch only when it is compared against '0' or '1'. An
# env var read for a path or a truthy presence check is a value, not a gate, and
# is deliberately out of scope.
CONTROL_VALUES = ('0', '1')
EXEMPT_MD = {'CHANGELOG.md'}
FENCE = re.compile(r'^\s*```')
ON_PHRASE = re.compile(r'\bon by default\b|\bships on\b|\benabled by default\b', re.I)
OFF_PHRASE = re.compile(
    r'\boff by default\b|\bships off\b|\bdisabled by default\b|\bopt in\b', re.I
)


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
    if node.func.attr not in ('get', 'getenv') or not node.args:
        return None
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.Name):
        return consts.get(arg.id)
    return None


def gates_in_source(text: str) -> dict[str, str]:
    """{gate name: control value} for one module.

    The control value is the one a reader is told to SET -- the opt-out of an
    on-by-default gate, the opt-in of an off-by-default one. `get(X) == '0'`
    guards an early return, so '0' turns it off and the gate ships on; `== '1'`
    guards the proceed path, so '1' turns it on and the gate ships off. `!=` is
    the same statement inverted."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    consts = module_constants(tree)
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        if not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
            continue
        name = _env_read_name(node.left, consts)
        comparator = node.comparators[0]
        if name is None or not isinstance(comparator, ast.Constant):
            continue
        if comparator.value not in CONTROL_VALUES:
            continue
        found[name] = comparator.value
    return found


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
        if line.strip():
            if not buf:
                start = lineno
            buf.append(line)
        elif buf:
            paragraphs.append((start, '\n'.join(buf)))
            buf = []
    if buf:
        paragraphs.append((start, '\n'.join(buf)))
    return paragraphs


def check_markdown(path: Path, gates: dict[str, str], rel: str) -> list[str]:
    findings = []
    text = path.read_text(encoding='utf-8')
    for start, para in prose_paragraphs(text):
        for gate, control in sorted(gates.items()):
            if gate not in para:
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
            if contradiction.search(para):
                findings.append(
                    f'{rel}:{start}: paragraph mentions {gate} and describes the '
                    f'opposite default; the gate ships {ships}'
                )
    return findings


def run(root: Path) -> list[str]:
    gates, findings = collect_gates(root)
    if not gates:
        return [*findings, 'no env gates found under plugins/; the scan resolved nothing']
    targets = sorted((root / 'plugins').rglob('*.md')) + sorted(root.glob('*.md'))
    for md in targets:
        if md.name in EXEMPT_MD or '__pycache__' in md.parts:
            continue
        findings.extend(check_markdown(md, gates, md.relative_to(root).as_posix()))
    return findings


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
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

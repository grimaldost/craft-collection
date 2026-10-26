"""Tests for check_gate_claims.py.

Contract under test:
- gate polarity is read from the guard, both directions and both operators;
- a constant-named gate (`ENV_GATE`, `NUDGE_GATE`) resolves to its literal;
- an env var that is not compared against '0'/'1' is a value, not a gate;
- prose contradicting the guard is a finding -- by wrong control value, and by
  an "off by default" phrase anywhere in the same paragraph;
- fenced code is exempt (a verification recipe legitimately sets the variable);
- CHANGELOG.md is exempt (a dated record of what was true then);
- the root README's Hooks table has one row per hook entry point in the plugins'
  hooks.json files, so a hook added without a row (or a row left after a hook
  is dropped) is a finding;
- the live repository is clean.

The red proof is `test_a_contradicting_doc_reddens_the_check`: it seeds the exact
defect that motivated the script -- a body saying the hook is off by default
while the guard says otherwise -- and watches the check exit non-zero. Without
it this file would assert only that a passing check passes.

Stdlib-runnable: `python test_check_gate_claims.py`.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_gate_claims as cgc

SCRIPT = Path(__file__).resolve().parent / 'check_gate_claims.py'
REPO = Path(__file__).resolve().parent.parent

ON_GUARD = "import os\nENV_GATE = 'DEMO_GATE'\n\n\ndef main():\n    if os.environ.get(ENV_GATE) == '0':\n        return 0\n    return 1\n"
OFF_GUARD = "import os\n\n\ndef main():\n    if os.environ.get('DEMO_GATE') == '1':\n        return 1\n    return 0\n"


# Three-valued gates. Each is classified by its unset value (the get() default, or
# the fall-through when there is none), never by whether 'observe' appears.
OBSERVE_DEFAULT = (
    "import os\nGATE = 'DEMO_GATE'\n\n\ndef mode():\n"
    "    value = os.environ.get(GATE, 'observe')\n"
    "    if value == '0':\n        return 'off'\n"
    "    if value == 'on':\n        return 'on'\n"
    "    return 'observe'\n"
)
OBSERVE_BY_TAIL = (
    "import os\n\n\ndef mode():\n    value = os.environ.get('DEMO_GATE')\n"
    "    if value == '0':\n        return 'off'\n"
    "    if value == 'on':\n        return 'on'\n"
    "    return 'observe'\n"
)
OBSERVE_BY_ELIMINATION = (
    "import os\n\n\ndef main():\n    value = os.environ.get('DEMO_GATE')\n"
    "    if value == '0':\n        return 0\n    record()\n"
    "    if value == 'on':\n        emit()\n    return 0\n"
)
# The section 5 and section 7 shape: '0' off, 'observe' logs only, unset on.
THREE_VALUED_ON = (
    "import os\n\n\ndef main():\n    value = os.environ.get('DEMO_GATE')\n"
    "    if value == '0':\n        return 0\n    observe = value == 'observe'\n"
    '    decide(observe)\n    return 0\n'
)
# The session-workflow 0.28.0 shape: a mode() whose fall-through is 'on'.
THREE_VALUED_ON_BY_TAIL = (
    "import os\nGATE = 'DEMO_GATE'\n\n\ndef mode():\n    value = os.environ.get(GATE)\n"
    "    if value == '0':\n        return 'off'\n"
    "    if value == 'observe':\n        return 'observe'\n"
    "    return 'on'\n"
)


def _plugin_tree(root: Path, guard: str, doc: str, doc_name: str = 'SKILL.md') -> None:
    skill = root / 'plugins' / 'demo' / 'skills' / 'demo' / 'scripts'
    skill.mkdir(parents=True)
    (skill / 'hook.py').write_text(guard, encoding='utf-8')
    (skill.parent / doc_name).write_text(doc, encoding='utf-8')


def run_cli(root: Path):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), str(root)],
        capture_output=True,
        encoding='utf-8',
        timeout=60,
    )


def test_polarity_is_read_from_the_guard():
    assert cgc.gates_in_source(ON_GUARD) == {'DEMO_GATE': '0'}
    assert cgc.gates_in_source(OFF_GUARD) == {'DEMO_GATE': '1'}


def test_not_equal_operator_is_the_same_statement_inverted():
    src = "import os\nif os.environ.get('R') != '0':\n    pass\n"
    assert cgc.gates_in_source(src) == {'R': '0'}


def test_a_value_read_is_not_a_gate():
    # Path overrides and truthiness checks are values, not boolean switches;
    # classifying them would invent defaults nobody documented.
    src = "import os\nD = os.environ.get('SOME_DIR')\nif os.environ.get('CLAUDECODE'):\n    pass\n"
    assert cgc.gates_in_source(src) == {}


def test_a_contradicting_doc_reddens_the_check():
    # THE RED PROOF. The observed defect, reproduced: the guard ships the hook
    # ON, and the body tells the reader it is off and to set =1 to enable it.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root,
            ON_GUARD,
            '# Demo\n\nAutomatic injection (env-gated, off by default): with\n`DEMO_GATE=1`, a hook runs.\n',
        )
        proc = run_cli(root)
        assert proc.returncode == 1, 'a false documented default must not pass'
        assert 'DEMO_GATE=1' in proc.stdout
        assert 'ships on' in proc.stdout


def test_an_opt_in_gate_documented_as_opt_out_also_reddens():
    # The mirror case, so the check is not accidentally one-directional.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(root, OFF_GUARD, '# Demo\n\nShips on. Opt out with `DEMO_GATE=0`.\n')
        proc = run_cli(root)
        assert proc.returncode == 1
        assert 'ships off' in proc.stdout


def test_correct_prose_passes():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(root, ON_GUARD, '# Demo\n\nShips on; `DEMO_GATE=0` opts out.\n')
        proc = run_cli(root)
        assert proc.returncode == 0, proc.stdout


def test_fenced_code_is_not_a_claim():
    # A verification recipe sets the variable deliberately. A check that could
    # not say that would push authors to delete the recipe.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root,
            ON_GUARD,
            '# Demo\n\nSimulate it:\n\n```sh\nDEMO_GATE=1 python hook.py\n```\n',
        )
        proc = run_cli(root)
        assert proc.returncode == 0, proc.stdout


def test_changelog_is_exempt():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root,
            ON_GUARD,
            '# Changelog\n\n## 0.8.0\n\nShipped behind `DEMO_GATE=1`, off by default.\n',
            doc_name='CHANGELOG.md',
        )
        proc = run_cli(root)
        assert proc.returncode == 0, proc.stdout


def test_conflicting_polarity_is_reported_not_skipped():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(root, ON_GUARD, '# Demo\n\nShips on; `DEMO_GATE=0` opts out.\n')
        other = root / 'plugins' / 'demo' / 'hooks'
        other.mkdir(parents=True)
        (other / 'other.py').write_text(OFF_GUARD, encoding='utf-8')
        proc = run_cli(root)
        assert proc.returncode == 1
        assert 'opt-out and opt-in' in proc.stdout


def test_an_empty_tree_does_not_pass_quietly():
    # Resolving no gates at all means the scan found nothing, which is a
    # failure to check -- not a clean bill of health.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / 'plugins').mkdir()
        proc = run_cli(root)
        assert proc.returncode == 1
        assert 'resolved nothing' in proc.stdout


def _hooks_tree(root: Path, commands: int, rows: int) -> None:
    """A plugin with `commands` hook entry points and a README table of `rows`."""
    _plugin_tree(root, ON_GUARD, '# Demo\n\nShips on; `DEMO_GATE=0` opts out.\n')
    hooks = root / 'plugins' / 'demo' / 'hooks'
    hooks.mkdir(parents=True)
    entries = [
        {'hooks': [{'type': 'command', 'command': 'uv', 'args': [f'h{i}']}]}
        for i in range(commands)
    ]
    (hooks / 'hooks.json').write_text(
        json.dumps({'hooks': {'SessionStart': entries}}), encoding='utf-8'
    )
    table = ''.join(f'| h{i} | on | `DEMO_GATE=0` |\n' for i in range(rows))
    (root / 'README.md').write_text(
        '# Root\n\n## Hooks\n\nSome prose.\n\n| Behaviour | Default | Opt out with |\n'
        '|-----------|---------|--------------|\n'
        + table
        + '\n## Next\n\n| a | b |\n|---|---|\n| x | y |\n',
        encoding='utf-8',
    )


def test_a_hooks_table_missing_a_row_reddens_the_check():
    # The observed defect: three table rows for nine hook entry points.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _hooks_tree(root, commands=3, rows=2)
        proc = run_cli(root)
        assert proc.returncode == 1, 'a table with fewer rows than hooks must not pass'
        assert 'Hooks table' in proc.stdout
        assert '2 row(s)' in proc.stdout and '3 hook entry point(s)' in proc.stdout


def test_a_hooks_table_with_one_row_per_hook_passes():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _hooks_tree(root, commands=3, rows=3)
        proc = run_cli(root)
        assert proc.returncode == 0, proc.stdout


def test_three_valued_gates_are_classified_by_their_unset_value():
    assert cgc.gates_in_source(OBSERVE_DEFAULT) == {'DEMO_GATE': 'observe'}
    assert cgc.gates_in_source(OBSERVE_BY_TAIL) == {'DEMO_GATE': 'observe'}
    assert cgc.gates_in_source(OBSERVE_BY_ELIMINATION) == {'DEMO_GATE': 'observe'}
    # 'observe' appears in both of these, and both still ship on.
    assert cgc.gates_in_source(THREE_VALUED_ON) == {'DEMO_GATE': '0'}
    assert cgc.gates_in_source(THREE_VALUED_ON_BY_TAIL) == {'DEMO_GATE': '0'}


def test_an_observe_default_gate_called_on_by_default_reddens():
    # The FM-9 defect: the pending-asks gate moved to observe by default, and prose
    # still saying "on by default" must not pass.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root,
            OBSERVE_DEFAULT,
            '# Demo\n\nThe gate is on by default; `DEMO_GATE=0` opts out.\n',
            doc_name='README.md',
        )
        proc = run_cli(root)
        assert proc.returncode == 1, proc.stdout
        assert 'DEMO_GATE' in proc.stdout and 'observe' in proc.stdout, proc.stdout


def test_an_observe_default_gate_called_observe_by_default_passes():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root,
            OBSERVE_DEFAULT,
            '# Demo\n\nObserve by default: it records and prints nothing. `DEMO_GATE=on`\n'
            'prints the advice and `DEMO_GATE=0` turns it off.\n',
            doc_name='README.md',
        )
        proc = run_cli(root)
        assert proc.returncode == 0, proc.stdout


def test_a_three_valued_on_gate_keeps_its_on_by_default_prose():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root,
            THREE_VALUED_ON,
            '# Demo\n\nOn by default; `DEMO_GATE=0` disables it and `DEMO_GATE=observe`\n'
            'logs without denying.\n',
        )
        proc = run_cli(root)
        assert proc.returncode == 0, proc.stdout


def test_an_on_gate_called_observe_by_default_reddens():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root, THREE_VALUED_ON, '# Demo\n\nObserve by default; `DEMO_GATE=0` opts out.\n'
        )
        proc = run_cli(root)
        assert proc.returncode == 1, proc.stdout
        assert 'ships on' in proc.stdout, proc.stdout


def test_an_observe_default_gate_documented_with_one_reddens():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root, OBSERVE_DEFAULT, '# Demo\n\nObserve by default; `DEMO_GATE=1` enables it.\n'
        )
        proc = run_cli(root)
        assert proc.returncode == 1, proc.stdout
        assert 'DEMO_GATE=1' in proc.stdout, proc.stdout


def test_a_list_item_or_table_row_is_its_own_claim():
    # A README lists hooks with different defaults as bullets of one list, or rows
    # of one table; one item's "on by default" is not a claim about the next one's gate.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root,
            OBSERVE_DEFAULT,
            '# Demo\n\n- Anchor hook. **On by default**; `OTHER_GATE=0` opts out.\n'
            '- Demo hook. Observe by default; `DEMO_GATE=on` prints and\n'
            '  `DEMO_GATE=0` turns it off.\n\n'
            '| Hook | Default | Control |\n|---|---|---|\n'
            '| other | on by default | `OTHER_GATE=0` |\n'
            '| demo | observe by default | `DEMO_GATE=0` |\n',
            doc_name='README.md',
        )
        proc = run_cli(root)
        assert proc.returncode == 0, proc.stdout


def test_a_wrapped_list_item_is_still_one_claim():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _plugin_tree(
            root,
            OBSERVE_DEFAULT,
            '# Demo\n\n- Demo hook, which ships\n  on by default with `DEMO_GATE=0`.\n',
            doc_name='README.md',
        )
        proc = run_cli(root)
        assert proc.returncode == 1, proc.stdout


def test_the_live_repository_is_clean():
    assert cgc.run(REPO) == []


if __name__ == '__main__':
    test_polarity_is_read_from_the_guard()
    test_not_equal_operator_is_the_same_statement_inverted()
    test_a_value_read_is_not_a_gate()
    test_a_contradicting_doc_reddens_the_check()
    test_an_opt_in_gate_documented_as_opt_out_also_reddens()
    test_correct_prose_passes()
    test_fenced_code_is_not_a_claim()
    test_changelog_is_exempt()
    test_conflicting_polarity_is_reported_not_skipped()
    test_an_empty_tree_does_not_pass_quietly()
    test_a_hooks_table_missing_a_row_reddens_the_check()
    test_a_hooks_table_with_one_row_per_hook_passes()
    test_three_valued_gates_are_classified_by_their_unset_value()
    test_an_observe_default_gate_called_on_by_default_reddens()
    test_an_observe_default_gate_called_observe_by_default_passes()
    test_a_three_valued_on_gate_keeps_its_on_by_default_prose()
    test_an_on_gate_called_observe_by_default_reddens()
    test_an_observe_default_gate_documented_with_one_reddens()
    test_a_list_item_or_table_row_is_its_own_claim()
    test_a_wrapped_list_item_is_still_one_claim()
    test_the_live_repository_is_clean()
    print('ok: all check_gate_claims tests passed')

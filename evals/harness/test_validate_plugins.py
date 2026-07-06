#!/usr/bin/env python3
"""Self-contained checks for scripts/validate_plugins.py (no pytest required).

`validate_plugins` imports PyYAML (used to catch the frontmatter colon-space trap),
so this test is skipped when PyYAML is not installed — run_tests.py stays stdlib-only,
and CI (which installs pyyaml) exercises it fully.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

try:
    import validate_plugins
except ImportError:
    validate_plugins = None


def _make_plugin(base: Path, *, hooks_json: str | None = None, skill_body: str = '') -> Path:
    (base / '.claude-plugin').mkdir(parents=True)
    (base / '.claude-plugin' / 'marketplace.json').write_text(
        '{"name":"m","owner":{"name":"x"},"plugins":[{"name":"p","source":"./plugins/p",'
        '"description":"d"}]}',
        encoding='utf-8',
    )
    pdir = base / 'plugins' / 'p'
    (pdir / '.claude-plugin').mkdir(parents=True)
    (pdir / '.claude-plugin' / 'plugin.json').write_text(
        '{"name":"p","version":"0.0.1","description":"d"}', encoding='utf-8'
    )
    skdir = pdir / 'skills' / 's'
    skdir.mkdir(parents=True)
    (skdir / 'SKILL.md').write_text(
        f'---\nname: s\ndescription: d\n---\n\n# S\n\n{skill_body}\n', encoding='utf-8'
    )
    if hooks_json is not None:
        (pdir / 'hooks').mkdir(parents=True)
        (pdir / 'hooks' / 'hooks.json').write_text(hooks_json, encoding='utf-8')
    return pdir


def _run(base: Path) -> list[str]:
    orig = validate_plugins.ROOT
    validate_plugins.ROOT = base
    try:
        return validate_plugins.validate()
    finally:
        validate_plugins.ROOT = orig


def test_invalid_hooks_json_is_flagged():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(base, hooks_json='{ this is not json')
        errs = _run(base)
    assert any('hooks.json: invalid JSON' in e for e in errs), errs


def test_unknown_event_and_missing_hook_script_flagged():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(
            base,
            hooks_json='{"hooks":{"NotAnEvent":[{"hooks":[{"type":"command","command":"uv",'
            '"args":["run","${CLAUDE_PLUGIN_ROOT}/hooks/gone.py"]}]}]}}',
        )
        errs = _run(base)
    assert any('unknown hook event "NotAnEvent"' in e for e in errs), errs
    assert any('referenced script missing: hooks/gone.py' in e for e in errs), errs


def test_dangling_plugin_root_reference_flagged():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(base, skill_body='Run `${CLAUDE_PLUGIN_ROOT}/scripts/gone.py` to check.')
        errs = _run(base)
    assert any('missing ${CLAUDE_PLUGIN_ROOT} reference scripts/gone.py' in e for e in errs), errs


def test_dangling_nested_reference_flagged():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(base, skill_body='See `references/sub/deep.md` for details.')
        errs = _run(base)
    assert any('missing reference references/sub/deep.md' in e for e in errs), errs


def test_hooks_json_top_level_array_flagged():
    # A top-level ARRAY used to coerce to {} and skip hook validation entirely.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(base, hooks_json='[{"hooks": {"Stop": []}}]')
        errs = _run(base)
    assert any('top-level' in e for e in errs), errs


def test_hooks_json_bare_event_map_flagged():
    # Events at the top level (missing the "hooks" wrapper) also skipped silently
    # — the misconfiguration most likely to happen by hand.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(
            base,
            hooks_json='{"Stop":[{"hooks":[{"type":"command","command":"x"}]}]}',
        )
        errs = _run(base)
    assert any('top-level' in e for e in errs), errs


def test_valid_plugin_has_no_errors():
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        pdir = _make_plugin(
            base,
            hooks_json='{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"uv",'
            '"args":["run","${CLAUDE_PLUGIN_ROOT}/hooks/ok.py"]}]}]}}',
        )
        (pdir / 'hooks' / 'ok.py').write_text('x = 1\n', encoding='utf-8')
        errs = _run(base)
    assert errs == [], errs


def test_marketplace_description_mismatch_flagged():
    # The same fact stated in two surfaces drifts silently: each marketplace
    # entry's description must equal its plugin.json description — the missing
    # twin of the bundled-scripts sync gate (a marketplace copy once lagged a
    # whole clause for four minor versions with no gate to notice).
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(base)
        (base / '.claude-plugin' / 'marketplace.json').write_text(
            '{"name":"m","owner":{"name":"x"},"plugins":[{"name":"p",'
            '"source":"./plugins/p","description":"stale copy"}]}',
            encoding='utf-8',
        )
        errs = _run(base)
    assert any('description' in e and 'differs' in e for e in errs), errs


def main() -> int:
    if validate_plugins is None:
        print('skip: validate_plugins (PyYAML not installed)')
        return 0
    test_invalid_hooks_json_is_flagged()
    test_unknown_event_and_missing_hook_script_flagged()
    test_dangling_plugin_root_reference_flagged()
    test_dangling_nested_reference_flagged()
    test_hooks_json_top_level_array_flagged()
    test_hooks_json_bare_event_map_flagged()
    test_valid_plugin_has_no_errors()
    test_marketplace_description_mismatch_flagged()
    print('ok: validate_plugins')
    return 0


if __name__ == '__main__':
    sys.exit(main())

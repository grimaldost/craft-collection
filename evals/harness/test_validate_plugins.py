#!/usr/bin/env python3
"""Self-contained checks for scripts/validate_plugins.py (no pytest required).

PyYAML is optional in the validator (frontmatter checks degrade without it),
so this module now runs stdlib-only under run_tests.py — the hook-event
allowlist, hooks.json shape, and reference-resolution assertions gate every
push instead of hiding behind a whole-module skip (the gap that let two real
gate issues stay invisible locally, 2026-07-23). Only the frontmatter-YAML
test self-guards on PyYAML's presence; CI (which installs pyyaml) runs it.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import validate_plugins  # noqa: E402 - sys.path set up first


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


def test_empirically_verified_events_accepted():
    # PostToolBatch / PostToolUseFailure / MessageDisplay were verified real by
    # the 2026-07-23 headless probes (docs/research/2026-07-22-claude-code-
    # hook-events.md); the allowlist must not reject a registration on them.
    for event in ('PostToolBatch', 'PostToolUseFailure', 'MessageDisplay'):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            hooks = {
                'hooks': {
                    event: [
                        {
                            'hooks': [
                                {
                                    'type': 'command',
                                    'command': 'uv',
                                    'args': ['run', '${CLAUDE_PLUGIN_ROOT}/hooks/ok.py'],
                                }
                            ]
                        }
                    ]
                }
            }
            pdir = _make_plugin(base, hooks_json=json.dumps(hooks))
            (pdir / 'hooks' / 'ok.py').write_text('x = 1\n', encoding='utf-8')
            errs = _run(base)
        assert not any('unknown hook event' in e for e in errs), (event, errs)


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


def test_bad_frontmatter_flagged_when_yaml_present():
    # The colon-space trap and friends need PyYAML; self-guard instead of
    # skipping the whole module (CI installs pyyaml and runs this).
    if validate_plugins.yaml is None:
        print('note: frontmatter-YAML case skipped (PyYAML not installed)')
        return
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        pdir = _make_plugin(base)
        (pdir / 'skills' / 's' / 'SKILL.md').write_text(
            '---\nname: s\ndescription: broken: colon space\n  bad indent\n---\n\n# S\n',
            encoding='utf-8',
        )
        errs = _run(base)
    assert any('bad frontmatter YAML' in e for e in errs), errs


def test_word_budget_follows_patched_root():
    # The T3b leak (bit twice: P1 wave, then the 0.20.0 build): the budget scan
    # ran against the REAL repo regardless of the patched ROOT, so fixture tests
    # failed whenever the working tree was transiently over budget. Contract:
    # a fixture tree WITHOUT scripts/word_budget.json gets no budget check; a
    # fixture tree WITH one is checked against ITS OWN skills.
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(base, skill_body='word ' * 50)
        errs = _run(base)
        assert not any('word_budget' in e or 'budget' in e for e in errs), errs
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        _make_plugin(base, skill_body='word ' * 50)
        (base / 'scripts').mkdir()
        (base / 'scripts' / 'word_budget.json').write_text(
            '{"plugins/p/skills/s/SKILL.md": 3}', encoding='utf-8'
        )
        errs = _run(base)
    assert any('> budget 3' in e for e in errs), (
        'fixture budget file ignored - the scan did not follow the patched ROOT',
        errs,
    )


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
    test_invalid_hooks_json_is_flagged()
    test_unknown_event_and_missing_hook_script_flagged()
    test_dangling_plugin_root_reference_flagged()
    test_dangling_nested_reference_flagged()
    test_hooks_json_top_level_array_flagged()
    test_hooks_json_bare_event_map_flagged()
    test_empirically_verified_events_accepted()
    test_valid_plugin_has_no_errors()
    test_bad_frontmatter_flagged_when_yaml_present()
    test_word_budget_follows_patched_root()
    test_marketplace_description_mismatch_flagged()
    print('ok: validate_plugins')
    return 0


if __name__ == '__main__':
    sys.exit(main())

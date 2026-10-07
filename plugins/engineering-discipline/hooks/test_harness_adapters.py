#!/usr/bin/env python3
"""Self-contained checks for harness_adapters.py (no pytest required)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import harness_adapters as ha


def main() -> int:
    # format_decision: only .py files in a project that declares ruff yield
    # commands; the scope and the commands both come from the ruff_format core,
    # so every harness formats exactly what the Claude Code hook formats.
    assert ha.format_decision(None) == []
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / '.git').mkdir()  # the repository boundary ends the config walk
        mod, notes = str(Path(td) / 'mod.py'), str(Path(td) / 'notes.md')
        assert ha.format_decision(notes) == []
        assert ha.format_decision(mod) == [], 'a repo without ruff config must not format'
        (Path(td) / 'ruff.toml').write_text('', encoding='utf-8')
        assert ha.format_decision(notes) == []
        cmds = ha.format_decision(mod)
        assert cmds == [['uvx', 'ruff', 'format', mod]], f'unexpected commands: {cmds}'

    # bash_verdict delegates to the uv_enforce core with real cwd detection.
    with tempfile.TemporaryDirectory() as td:
        assert ha.bash_verdict('pip install requests', td) == 'allow', 'non-uv cwd must allow'
        (Path(td) / 'uv.lock').write_text('', encoding='utf-8')
        assert ha.bash_verdict('pip install requests', td) == 'block', 'uv cwd must block'
        assert ha.bash_verdict('uv add requests', td) == 'allow', 'uv itself must pass'
        assert ha.bash_verdict('pip install requests', td, allow_override=True) == 'allow', (
            'override must allow'
        )

    # The block message is non-empty, harness-neutral guidance (no CC env var).
    msg = ha.block_message()
    assert 'uv add' in msg and 'CLAUDE' not in msg, 'message must be harness-neutral'

    # parse_json_payload wraps the tolerant reader: dict in, {} on garbage.
    assert ha.parse_json_payload('{"a": 1}') == {'a': 1}
    assert ha.parse_json_payload('') == {}
    assert ha.parse_json_payload('not json') == {}
    assert ha.parse_json_payload('[1, 2]') == {}

    # CC adapters translate the CC envelope to plain core inputs.
    assert ha.claude_code_edited_file({'tool_input': {'file_path': 'x/y.py'}}) == 'x/y.py'
    assert ha.claude_code_edited_file({'tool_input': {'file_path': 'x/y.md'}}) is None
    assert ha.claude_code_bash_command({'tool_input': {'command': 'ls'}}) == 'ls'
    assert ha.claude_code_bash_command({}) == ''

    print('ok: harness_adapters wraps cores in place; CC adapters translate only')
    return 0


if __name__ == '__main__':
    sys.exit(main())

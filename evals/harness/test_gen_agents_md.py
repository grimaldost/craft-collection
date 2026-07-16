#!/usr/bin/env python3
"""Self-contained checks for scripts/gen_agents_md.py (no pytest required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import gen_agents_md  # noqa: E402


def main() -> int:
    text = gen_agents_md.render()

    # Determinism: two renders are byte-identical.
    assert text == gen_agents_md.render(), 'render is not deterministic'

    # Banner names the generator and forbids hand edits.
    first = text.splitlines()[0]
    assert 'GENERATED' in first and 'gen_agents_md.py' in first, 'banner missing/incomplete'

    # Population: every SKILL.md, command, and output style is listed with its path.
    skills = sorted(ROOT.glob('plugins/*/skills/*/SKILL.md'))
    assert len(skills) == 23, f'expected 23 skills in the tree, found {len(skills)}'
    for md in (
        skills
        + sorted(ROOT.glob('plugins/*/commands/*.md'))
        + sorted(ROOT.glob('plugins/*/output-styles/*.md'))
    ):
        rel = md.relative_to(ROOT).as_posix()
        assert f'(`{rel}`)' in text, f'{rel} missing from the index'

    # Every entry line carries a non-empty description (no bare "— (" collapse).
    for line in text.splitlines():
        if line.startswith('- **'):
            assert '— (' not in line, f'entry with empty description: {line[:60]}'

    # Byte hygiene: no trailing whitespace; exactly one trailing newline.
    assert all(line == line.rstrip() for line in text.splitlines()), 'trailing whitespace'
    assert text.endswith('\n') and not text.endswith('\n\n'), 'must end with exactly one newline'

    # --check agrees with the committed file (freshness gate contract).
    committed = (ROOT / 'AGENTS.md').read_text(encoding='utf-8')
    assert committed == text, 'committed AGENTS.md is stale — regenerate'

    print('ok: gen_agents_md determinism, population, hygiene, freshness')
    return 0


if __name__ == '__main__':
    sys.exit(main())

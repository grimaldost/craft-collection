#!/usr/bin/env python3
"""Self-contained checks for scripts/gen_agents_md.py (no pytest required)."""

from __future__ import annotations

import sys
import tempfile
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
    assert len(skills) == 25, f'expected 25 skills in the tree, found {len(skills)}'
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

    # The GATE half, made to fail on purpose. Everything above asserts the
    # generator renders correctly; nothing asserted that `--check` REJECTS a
    # stale file, so the one branch that blocks a commit had no red proof and
    # could have returned 0 unconditionally without a test noticing.
    real_output = gen_agents_md.OUTPUT
    with tempfile.TemporaryDirectory() as d:
        stale = Path(d) / 'AGENTS.md'
        stale.write_text('# AGENTS\n\nnot the generated index\n', encoding='utf-8')
        gen_agents_md.OUTPUT = stale
        try:
            assert gen_agents_md.main(['--check']) == 1, '--check passed over a stale AGENTS.md'
            # a missing file is stale too, not an empty pass
            stale.unlink()
            assert gen_agents_md.main(['--check']) == 1, '--check passed with no AGENTS.md at all'
        finally:
            gen_agents_md.OUTPUT = real_output
    assert gen_agents_md.main(['--check']) == 0, '--check rejected the real, fresh AGENTS.md'

    print('ok: gen_agents_md determinism, population, hygiene, freshness, stale-rejection')
    return 0


if __name__ == '__main__':
    sys.exit(main())

"""Tests for make_isolated_config's credentials-only copy. Runnable with pytest
or `python test_isolated_config.py`."""

from __future__ import annotations

import tempfile
from pathlib import Path

from claude_runner import cleanup_dir, make_isolated_config


def test_copies_credentials_only():
    real = Path(tempfile.mkdtemp(prefix='fake_claude_'))
    dest = None
    try:
        # A realistic ~/.claude top level: credentials plus the leak vectors.
        (real / '.credentials.json').write_text('{"token": "x"}', encoding='utf-8')
        (real / 'CLAUDE.md').write_text('| keel | C:/real/keel | docs/feedback |', encoding='utf-8')
        (real / 'settings.json').write_text(
            '{"permissions": {"allow": ["Write"]}}', encoding='utf-8'
        )
        (real / 'history.jsonl').write_text('{"prompt": "secret"}', encoding='utf-8')
        (real / 'stats-cache.json').write_text('{}', encoding='utf-8')
        (real / 'plugins').mkdir()

        dest = make_isolated_config(str(real))
        copied = sorted(p.name for p in Path(dest).iterdir())
        assert copied == ['.credentials.json'], copied
        assert (Path(dest) / '.credentials.json').read_text(encoding='utf-8') == '{"token": "x"}'
    finally:
        cleanup_dir(str(real))
        if dest:
            cleanup_dir(dest)


def test_missing_credential_yields_empty_config():
    real = Path(tempfile.mkdtemp(prefix='fake_claude_'))
    dest = None
    try:
        (real / 'CLAUDE.md').write_text('leak', encoding='utf-8')
        dest = make_isolated_config(str(real))
        assert list(Path(dest).iterdir()) == []  # nothing copied; smoke gate catches dead auth
    finally:
        cleanup_dir(str(real))
        if dest:
            cleanup_dir(dest)


if __name__ == '__main__':
    test_copies_credentials_only()
    test_missing_credential_yields_empty_config()
    print('ok: all isolated_config tests passed')

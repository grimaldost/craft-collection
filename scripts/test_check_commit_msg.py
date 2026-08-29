"""Tests for check_commit_msg.py.

Contract under test:
- a Co-Authored-By trailer crediting an AI tool is a finding; a human
  co-author trailer is not;
- a standalone "Generated with <tool>" badge line is a finding, robot-emoji
  and markdown-link variants included;
- editor-template comment lines are not part of the message;
- a clean conventional message passes;
- a wrong argv or an unreadable file is exit 2, never a quiet pass.

The red proof is `test_an_ai_attribution_trailer_exits_1`: it feeds the CLI a
message file carrying the exact trailer the rule exists to reject and watches
it exit 1.

Stdlib-runnable: `python test_check_commit_msg.py`.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_commit_msg as ccm

SCRIPT = Path(__file__).resolve().parent / 'check_commit_msg.py'


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_trailer_shapes_are_findings_and_a_human_coauthor_is_not():
    assert ccm.findings('fix: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n')
    assert ccm.findings('fix: x\n\nco-authored-by: GPT-5 <bot@example.com>\n')
    assert not ccm.findings('fix: x\n\nCo-Authored-By: Jane Doe <jane@example.com>\n')


def test_generated_with_badge_lines_are_findings():
    assert ccm.findings('fix: x\n\nGenerated with Claude\n')
    assert ccm.findings(
        'fix: x\n\n\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)\n'
    )
    assert ccm.findings('fix: x\n\ngenerated with Anthropic tooling\n')
    # the badge is named, not any sentence containing 'generated'
    assert not ccm.findings('fix: x\n\nThe scaffold generated with defaults is unchanged.\n')


def test_comment_lines_and_clean_messages_pass():
    assert not ccm.findings('# Generated with Claude -- editor template comment\nfix: x\n')
    assert not ccm.findings('feat(scripts): add the thing\n\nA plain body.\n')


def test_findings_output_is_ascii_even_for_an_emoji_line():
    found = ccm.findings('fix: x\n\n\U0001f916 Generated with Claude\n')
    assert found and all(ord(ch) < 128 for line in found for ch in line)


def test_an_ai_attribution_trailer_exits_1():
    """The red proof: the exact trailer the rule rejects, watched to fail."""
    with tempfile.TemporaryDirectory() as td:
        msg = Path(td) / 'COMMIT_EDITMSG'
        msg.write_text(
            'fix: x\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n', encoding='utf-8'
        )
        proc = run_cli(str(msg))
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'AI attribution' in proc.stdout


def test_a_clean_message_exits_0():
    with tempfile.TemporaryDirectory() as td:
        msg = Path(td) / 'COMMIT_EDITMSG'
        msg.write_text('feat(scripts): add the thing\n', encoding='utf-8')
        proc = run_cli(str(msg))
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_wrong_argv_and_missing_file_are_exit_2():
    assert run_cli().returncode == 2
    assert run_cli('no', 'such').returncode == 2
    assert run_cli(str(SCRIPT.parent / 'no_such_message_file')).returncode == 2


if __name__ == '__main__':
    for _name, _fn in sorted(globals().items()):
        if _name.startswith('test_') and callable(_fn):
            _fn()
    print('ok: all check_commit_msg tests passed')

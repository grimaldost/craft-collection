"""Tests for check_red_exception.py.

Contract under test:
- a SKILL.md missing the non-executable-artifact exception reddens the check
  (the red proof: the shipped body before T86a landed had none of this);
- a SKILL.md with the exception worded but no code exclusion also reddens --
  the boundary ("code stays on delete-and-redo") is a separate claim from the
  substitution itself, and either can be lost independently in a later edit;
- the live skill document carries both and passes.

Stdlib-runnable: `python test_check_red_exception.py`.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_red_exception as cre

SCRIPT = Path(__file__).resolve().parent / 'check_red_exception.py'
LIVE_SKILL_DIR = Path(__file__).resolve().parent.parent

BEFORE_T86A = (
    '---\nname: test-driven-development\ndescription: "..."\n---\n\n'
    '## If code exists before its test\n\n'
    'Delete it and start from the test.\n'
)

WITH_EXCEPTION_NO_BOUNDARY = BEFORE_T86A + (
    "\n**Exception, non-executable artifacts only**: restore the artifact's "
    'previous version from version control, watch the new assertions fail '
    'against it, then restore the change.\n'
)

WITH_EXCEPTION_AND_BOUNDARY = WITH_EXCEPTION_NO_BOUNDARY + ('\nCode has no such substitute.\n')


def _skill_dir(root: Path, text: str) -> Path:
    skill = root / 'skill'
    skill.mkdir()
    (skill / 'SKILL.md').write_text(text, encoding='utf-8')
    return skill


def run_cli(skill_dir: Path):
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), str(skill_dir)],
        capture_output=True,
        encoding='utf-8',
        timeout=60,
    )


def test_a_body_with_no_exception_reddens_the_check():
    # THE RED PROOF. The shipped SKILL.md before T86a had none of this text;
    # this reproduces that state and watches the check reject it.
    with tempfile.TemporaryDirectory() as d:
        skill_dir = _skill_dir(Path(d), BEFORE_T86A)
        proc = run_cli(skill_dir)
        assert proc.returncode == 1, 'a body with no exception must not pass'
        assert 'non-executable artifacts only' in proc.stdout


def test_an_exception_with_no_code_boundary_also_reddens():
    with tempfile.TemporaryDirectory() as d:
        skill_dir = _skill_dir(Path(d), WITH_EXCEPTION_NO_BOUNDARY)
        proc = run_cli(skill_dir)
        assert proc.returncode == 1, 'losing the code boundary must not pass'
        assert 'code exclusion is missing' in proc.stdout


def test_the_worded_and_bounded_exception_passes():
    with tempfile.TemporaryDirectory() as d:
        skill_dir = _skill_dir(Path(d), WITH_EXCEPTION_AND_BOUNDARY)
        proc = run_cli(skill_dir)
        assert proc.returncode == 0, proc.stdout


def test_a_missing_skill_md_is_a_finding_not_a_crash():
    with tempfile.TemporaryDirectory() as d:
        empty = Path(d) / 'empty'
        empty.mkdir()
        proc = run_cli(empty)
        assert proc.returncode == 1
        assert 'not found' in proc.stdout


def test_the_live_skill_document_passes():
    assert cre.run(LIVE_SKILL_DIR) == []


if __name__ == '__main__':
    test_a_body_with_no_exception_reddens_the_check()
    test_an_exception_with_no_code_boundary_also_reddens()
    test_the_worded_and_bounded_exception_passes()
    test_a_missing_skill_md_is_a_finding_not_a_crash()
    test_the_live_skill_document_passes()
    print('ok: all check_red_exception tests passed')

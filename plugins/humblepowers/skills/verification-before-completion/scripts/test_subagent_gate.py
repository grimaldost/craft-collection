"""Tests for the opt-in SubagentStop verification gate.

Runnable with pytest or `python test_subagent_gate.py`.

The gate is the one delivery mechanism for this skill with measured lift, and
the two things that make it safe to ship are mechanical, so they are asserted
here rather than described: it is silent unless armed, and it fails open. The
third — the wording — is asserted byte-for-byte, because the arm that was
measured clean on false positives differs from the arm that was rejected only
in its words.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

GATE = Path(__file__).resolve().parent / 'subagent_gate.py'

# The wording measured as `subagent-generic-gate`, verbatim. Duplicated here on
# purpose: this literal is the regression anchor, so an edit to the shipped
# string has to come here too and face the question of what it is now measuring.
MEASURED_REASON = (
    'Before you finish: are you actually confident this is correct, or are you '
    'assuming it is? Take one more pass over what you changed and satisfy yourself '
    'that it genuinely works and that you would find out if it stopped working.'
)

ARM = 'HUMBLEPOWERS_VERIFICATION_SUBAGENT_GATE'
STATE = 'HUMBLEPOWERS_VERIFICATION_GATE_STATE_DIR'
SKIP_MODELS = 'HUMBLEPOWERS_VERIFICATION_GATE_SKIP_MODELS'


def _run(payload, *, env_extra: dict[str, str], raw: str | None = None):
    env = {k: v for k, v in os.environ.items() if not k.startswith('HUMBLEPOWERS_')}
    env.update(env_extra)
    stdin = raw if raw is not None else json.dumps(payload)
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(GATE)],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def _armed(state: Path, **extra: str) -> dict[str, str]:
    return {ARM: '1', STATE: str(state), **extra}


def _decision(proc) -> dict:
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def test_disarmed_by_default():
    """A stop-blocking hook on every subagent is a bigger bet than one bank of
    evidence funds, so an unset variable means silence, not a block."""
    with tempfile.TemporaryDirectory() as td:
        proc = _run({'session_id': 's', 'agent_id': 'a'}, env_extra={STATE: td})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == '', proc.stdout


def test_armed_blocks_the_first_stop():
    with tempfile.TemporaryDirectory() as td:
        proc = _run({'session_id': 's', 'agent_id': 'a'}, env_extra=_armed(Path(td)))
    assert proc.returncode == 0, proc.stderr
    assert _decision(proc).get('decision') == 'block'


def test_reason_is_the_measured_wording_verbatim():
    with tempfile.TemporaryDirectory() as td:
        proc = _run({'session_id': 's', 'agent_id': 'a'}, env_extra=_armed(Path(td)))
    assert _decision(proc).get('reason') == MEASURED_REASON


def test_second_stop_of_the_same_subagent_passes():
    """One-shot per (session_id, agent_id): the block cannot loop."""
    with tempfile.TemporaryDirectory() as td:
        payload = {'session_id': 's', 'agent_id': 'a'}
        first = _run(payload, env_extra=_armed(Path(td)))
        second = _run(payload, env_extra=_armed(Path(td)))
    assert _decision(first).get('decision') == 'block'
    assert second.stdout.strip() == '', second.stdout


def test_each_subagent_gets_its_own_one_shot():
    """Concurrent trials share a session; keying on the session alone would let
    the first subagent's block silence every sibling's."""
    with tempfile.TemporaryDirectory() as td:
        a = _run({'session_id': 's', 'agent_id': 'a'}, env_extra=_armed(Path(td)))
        b = _run({'session_id': 's', 'agent_id': 'b'}, env_extra=_armed(Path(td)))
    assert _decision(a).get('decision') == 'block'
    assert _decision(b).get('decision') == 'block'


def test_fails_open_on_malformed_stdin():
    with tempfile.TemporaryDirectory() as td:
        proc = _run(None, env_extra=_armed(Path(td)), raw='not json at all {{{')
    assert proc.returncode == 0, proc.stderr


def test_fails_open_when_the_state_dir_is_unusable():
    """An unwritable counter must not turn into a subagent that cannot stop."""
    with tempfile.TemporaryDirectory() as td:
        blocker = Path(td) / 'not-a-dir'
        blocker.write_text('x', encoding='utf-8')
        proc = _run({'session_id': 's', 'agent_id': 'a'}, env_extra=_armed(blocker))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == '', proc.stdout


def test_tier_predicate_is_inert_unless_configured():
    """PROVISIONAL surface. Unset means no tier conditioning whatsoever — the
    measurement that would license one is not in."""
    with tempfile.TemporaryDirectory() as td:
        proc = _run(
            {'session_id': 's', 'agent_id': 'a', 'model': 'claude-opus-5'},
            env_extra=_armed(Path(td)),
        )
    assert _decision(proc).get('decision') == 'block'


def test_tier_predicate_skips_a_named_model():
    with tempfile.TemporaryDirectory() as td:
        env = _armed(Path(td), **{SKIP_MODELS: 'opus'})
        skipped = _run(
            {'session_id': 's', 'agent_id': 'a', 'model': 'claude-opus-5'}, env_extra=env
        )
        kept = _run(
            {'session_id': 's', 'agent_id': 'b', 'model': 'claude-haiku-4-5'}, env_extra=env
        )
    assert skipped.stdout.strip() == '', skipped.stdout
    assert _decision(kept).get('decision') == 'block'


def test_tier_predicate_gates_when_the_payload_names_no_model():
    """The SubagentStop payload's model key is unconfirmed. An absent model must
    fall back to the measured behaviour (gate), never to a silent no-op that
    would look like a clean false-positive rate it never earned."""
    with tempfile.TemporaryDirectory() as td:
        env = _armed(Path(td), **{SKIP_MODELS: 'opus'})
        proc = _run({'session_id': 's', 'agent_id': 'a'}, env_extra=env)
    assert _decision(proc).get('decision') == 'block'


def test_stale_markers_are_pruned():
    """The one deliberate divergence from the measured fixture: counters older
    than the retention window are removed, so an opt-in hook does not leave an
    unbounded trail of files in the user's temp dir."""
    with tempfile.TemporaryDirectory() as td:
        state = Path(td)
        stale = state / 'old-old.txt'
        stale.write_text('1', encoding='utf-8')
        os.utime(stale, (0, 0))
        fresh = state / 's-a.txt'
        _run({'session_id': 's', 'agent_id': 'a'}, env_extra=_armed(state))
        # Asserted INSIDE the block: outside it the TemporaryDirectory is already
        # gone, so `not stale.exists()` holds whatever the gate did — the check
        # passed against a missing gate.py before this line moved in.
        assert not stale.exists(), 'stale marker survived the prune'
        assert fresh.is_file(), 'the prune ate the counter it had just written'


def test_the_hook_is_actually_registered_at_this_path():
    """The corpus instance this guards against: a hook documented in three places
    that had never fired, because no document can tell you whether the harness
    reads it. Registration is a fact about hooks.json, so assert it there."""
    hooks = json.loads((GATE.parents[3] / 'hooks' / 'hooks.json').read_text(encoding='utf-8'))
    groups = hooks['hooks']['SubagentStop']
    args = [a for g in groups for h in g['hooks'] for a in h.get('args', [])]
    wanted = '${CLAUDE_PLUGIN_ROOT}/skills/verification-before-completion/scripts/subagent_gate.py'
    assert wanted in args, f'SubagentStop does not point at the gate: {args}'


if __name__ == '__main__':
    failures = 0
    for _name, _fn in sorted(globals().items()):
        if _name.startswith('test_') and callable(_fn):
            try:
                _fn()
            except AssertionError as exc:
                failures += 1
                print(f'FAIL {_name}: {exc}')
    if failures:
        sys.exit(1)
    print('ok: subagent verification gate checks passed')

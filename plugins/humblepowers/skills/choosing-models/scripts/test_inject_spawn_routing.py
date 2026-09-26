"""Tests for inject_spawn_routing.py - the PreToolUse spawn-time routing hint.

Contract under test:
- ON by default; HUMBLEPOWERS_SPAWN_ROUTING_HINT=0 is the documented opt-out;
- fires on a spawn that names no model (the agent inherits the session's, which
  is the measured failure: 43 subagents at inherited frontier tiers, and a
  139-agent programme routed by nothing);
- SILENT on a spawn that names a model - that decision was already taken;
- on `Workflow`, which has no top-level `model`, the script is read (inline
  `script`, or the file at `scriptPath`) and the hint fires only when some
  `agent()` call names no model; a script it cannot read or resolve keeps the
  hint, because unsure must not become silent;
- at most one hint per session per cooldown window, so a fan-out is reminded
  once at the script rather than once per agent;
- never emits a permissionDecision: an advisory hook must not change whether a
  tool call is allowed, and `allow` would skip a prompt the user wanted;
- ASCII-only output, and every path exits 0 (a PreToolUse hook that errors or
  hangs costs the tool call).

Stdlib-runnable (no pytest required): `python test_inject_spawn_routing.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'inject_spawn_routing.py'


def run_hook(
    state: Path,
    tool_name: str = 'Agent',
    tool_input: dict | None = None,
    session: str = 's1',
    gate: str | None = None,
    raw: str | None = None,
    cwd: str | None = None,
):
    env = dict(os.environ)
    env.pop('HUMBLEPOWERS_SPAWN_ROUTING_HINT', None)
    if gate is not None:
        env['HUMBLEPOWERS_SPAWN_ROUTING_HINT'] = gate
    env['HUMBLEPOWERS_SPAWN_HINT_STATE_DIR'] = str(state)
    payload = (
        raw
        if raw is not None
        else json.dumps(
            {
                'hook_event_name': 'PreToolUse',
                'session_id': session,
                'tool_name': tool_name,
                'tool_input': tool_input if tool_input is not None else {'subagent_type': 'x'},
                **({'cwd': cwd} if cwd is not None else {}),
            }
        )
    )
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, str(SCRIPT), '--pre-tool-use'],
        input=payload,
        capture_output=True,
        encoding='utf-8',
        env=env,
        timeout=30,
    )


def _ctx(proc) -> str:
    return json.loads(proc.stdout)['hookSpecificOutput']['additionalContext']


def test_it_fires_at_the_spawn_with_no_env_set():
    """The activation test for the whole row. `choosing-models` took ZERO
    invocations across a 40-hour, 139-subagent programme under a written owner
    order repeated three times; prose had already failed. A hook nobody enables
    would fail the same way, so this ships ON and an install that sets nothing
    must still see the hint."""
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d))
        assert proc.returncode == 0, proc.stderr
        ctx = _ctx(proc)
        assert 'choosing-models' in ctx
        assert '(model, effort)' in ctx, 'the activation test must be the payload'


def test_the_opt_out_silences_it():
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), gate='0')
        assert proc.returncode == 0
        assert proc.stdout.strip() == ''


def test_a_spawn_that_already_names_a_model_is_left_alone():
    # `model` is present in tool_input only when the caller passed it, so its
    # presence IS the evidence that the decision was taken. Reminding there is
    # the noise that gets hooks switched off.
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_input={'subagent_type': 'x', 'model': 'haiku'})
        assert proc.returncode == 0
        assert proc.stdout.strip() == ''


def test_a_fan_out_is_reminded_once_not_once_per_agent():
    # The mechanism's whole claim to scale: one 54-item fan-out costs one hint.
    with tempfile.TemporaryDirectory() as d:
        state = Path(d)
        assert run_hook(state).stdout.strip() != ''
        for _ in range(5):
            assert run_hook(state).stdout.strip() == ''


def test_a_different_session_gets_its_own_hint():
    with tempfile.TemporaryDirectory() as d:
        state = Path(d)
        assert run_hook(state, session='s1').stdout.strip() != ''
        assert run_hook(state, session='s2').stdout.strip() != ''


def test_the_batch_counter_rule_travels_with_the_hint():
    # Every one of twenty un-routed dispatches found its alibi in the skill's
    # single-task exception while the work ran in lots of 4, 5, 6, 13 and 34.
    with tempfile.TemporaryDirectory() as d:
        assert 'batch' in _ctx(run_hook(Path(d))).lower()


def test_it_never_decides_the_permission():
    # An advisory hook that returned `allow` would skip a permission prompt the
    # user configured; one that returned `ask` or `deny` would block work over a
    # reminder. The documented advisory shape is additionalContext with no
    # permissionDecision at all.
    with tempfile.TemporaryDirectory() as d:
        out = json.loads(run_hook(Path(d)).stdout)
        assert 'permissionDecision' not in out['hookSpecificOutput']
        assert 'permissionDecisionReason' not in out['hookSpecificOutput']
        assert out['hookSpecificOutput']['hookEventName'] == 'PreToolUse'


def test_a_tool_that_is_not_a_spawn_surface_is_silent():
    # The matcher filters by tool_name, but a hook that trusted it would emit on
    # any misconfiguration. TaskCreate/TaskGet are the todo system, not spawns.
    with tempfile.TemporaryDirectory() as d:
        state = Path(d)
        assert run_hook(state, tool_name='Bash', tool_input={'command': 'ls'}).stdout.strip() == ''
        assert run_hook(state, tool_name='TaskCreate').stdout.strip() == ''


def test_every_failure_path_exits_zero_and_says_nothing():
    # A PreToolUse hook that exits non-zero or hangs costs the tool call. Garbage
    # stdin, empty stdin, and an unwritable state dir all fail open.
    with tempfile.TemporaryDirectory() as d:
        for raw in ('not json at all', '', '[]', '{"tool_input": "not a dict"}'):
            proc = run_hook(Path(d), raw=raw)
            assert proc.returncode == 0, raw
            assert proc.stdout.strip() == '', raw
    # a state dir that cannot be created must not cost the hint either
    proc = run_hook(Path(SCRIPT) / 'not-a-directory')
    assert proc.returncode == 0
    assert proc.stdout.strip() != '', 'unwritable state must fail toward the reminder'


def test_the_payload_is_ascii_for_a_codepage_limited_console():
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d))
        proc.stdout.encode('ascii')


# --- Workflow: the routing lives inside the script, per agent() call --------
#
# The Workflow tool has no top-level `model` field, so the Agent-shaped
# predicate fired on every workflow launch, routed or not (2026-09-17 report:
# eight agent() calls, each with model and effort, drew the "names no model"
# hint). A signal that fires on every script trains the reader to ignore it.

ROUTED_SCRIPT = """export const meta = {
  name: 'batch',
  description: 'summarize then verify',
  phases: [{ title: 'Summarize' }, { title: 'Verify', model: 'opus' }],
}
const SCHEMA = { type: 'object', properties: { model: { type: 'string' } } }
phase('Summarize')
const notes = await parallel(ITEMS.map(i => () =>
  agent(`Summarize ${i}. Do not call agent( yourself.`, { model: 'sonnet', effort: 'low' })))
const verdicts = await pipeline(notes, n =>
  agent('Try to refute: ' + n, {
    label: 'verify',
    schema: SCHEMA,
    'model': 'sonnet',
    effort: 'medium',
  }))
return verdicts
"""

UNROUTED_ONE = ROUTED_SCRIPT.replace(
    'return verdicts',
    "// a comment that says model: 'haiku' is not an option\n"
    "const critic = await agent('What is missing?', { label: 'critic', schema: SCHEMA })\n"
    'return verdicts',
)


def test_a_workflow_whose_every_agent_call_names_a_model_is_left_alone():
    # Includes the traps a substring count falls into: a prompt that mentions
    # `agent(`, a meta phase entry carrying `model` (display only), a schema
    # with a property named `model`, and a quoted `'model'` key.
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Workflow', tool_input={'script': ROUTED_SCRIPT})
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == '', proc.stdout


def test_a_workflow_with_one_agent_call_that_names_no_model_fires():
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Workflow', tool_input={'script': UNROUTED_ONE})
        assert proc.returncode == 0, proc.stderr
        ctx = _ctx(proc)
        assert 'choosing-models' in ctx
        assert '1 of 3 agent() calls' in ctx, ctx


def test_an_agent_spawn_without_a_model_still_fires():
    # The Agent-tool behaviour is unchanged: no `model` field is the signal.
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Agent', tool_input={'subagent_type': 'x'})
        assert proc.returncode == 0, proc.stderr
        assert 'This spawn names no model' in _ctx(proc)


def test_a_workflow_script_is_read_from_script_path_relative_to_cwd():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / 'wf').mkdir()
        (root / 'wf' / 'routed.js').write_text(ROUTED_SCRIPT, encoding='utf-8')
        (root / 'wf' / 'unrouted.js').write_text(UNROUTED_ONE, encoding='utf-8')
        routed = run_hook(
            root / 'state-a',
            tool_name='Workflow',
            tool_input={'scriptPath': 'wf/routed.js'},
            cwd=str(root),
        )
        assert routed.stdout.strip() == '', routed.stdout
        absolute = run_hook(
            root / 'state-b',
            tool_name='Workflow',
            tool_input={'scriptPath': str(root / 'wf' / 'unrouted.js')},
        )
        assert '1 of 3 agent() calls' in _ctx(absolute)


def test_a_workflow_it_cannot_read_fails_toward_the_hint():
    # Unsure is not silent: a missing file, a saved workflow launched by name,
    # and a script that runs another workflow all keep the reminder.
    nested = ROUTED_SCRIPT.replace('return verdicts', "return workflow('other-batch')")
    cases = (
        {'scriptPath': 'no/such/file.js'},
        {'name': 'saved-batch'},
        {'script': nested},
        {'script': 'const x = 1\n'},
        {'script': "agent('unterminated, { model: 'sonnet' })"},
    )
    for i, tool_input in enumerate(cases):
        with tempfile.TemporaryDirectory() as d:
            proc = run_hook(Path(d), tool_name='Workflow', tool_input=tool_input)
            assert proc.returncode == 0, (tool_input, proc.stderr)
            assert 'choosing-models' in _ctx(proc), (i, tool_input)


def test_a_regex_literal_holding_a_quote_does_not_break_the_parse():
    # Real workflow scripts validate args with regex literals such as
    # /[`\n\r]/ - a quote or backtick inside one must not open a string.
    script = ROUTED_SCRIPT.replace(
        'phase(',
        "if (/[`'\\n]/.test(args.x) || /\\//.test(args.y)) log('odd')\n"
        'const half = total / 2 / 1\n'
        'phase(',
        1,
    )
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Workflow', tool_input={'script': script})
        assert proc.stdout.strip() == '', proc.stdout


def test_shared_options_resolve_through_a_const_and_a_spread():
    script = (
        "const CHEAP = { model: 'haiku', effort: 'low' }\n"
        "const a = await agent('one', CHEAP)\n"
        "const b = await agent('two', { ...CHEAP, label: 'two' })\n"
        "const c = await agent('three', { model })\n"
    )
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Workflow', tool_input={'script': script})
        assert proc.stdout.strip() == '', proc.stdout
    unresolved = 'async function run(p, opts) { return agent(p, opts) }\n'
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Workflow', tool_input={'script': unresolved})
        assert '1 of 1 agent() calls' in _ctx(proc)


def test_options_built_by_a_route_helper_count_as_routed():
    # The shape this skill's own emission guidance produces: score first, resolve the
    # (model, effort) pair once, then spread it into each call. The hook cannot evaluate
    # the call, but a spread of one is a decision taken in the script, not an inherited
    # default - reporting it as "inherits this session tier" was false (T93b).
    routed = (
        'const R = id => ({ model: routes[id].model, effort: routes[id].effort })\n'
        "await agent('one', { label: 'one', ...R('one') })\n"
        "await agent('two', { ...R('two'), phase: 'Work' })\n"
    )
    mixed = routed + "await agent('three', { label: 'three' })\n"
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Workflow', tool_input={'script': routed})
        assert proc.stdout.strip() == '', proc.stdout
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Workflow', tool_input={'script': mixed})
        assert '1 of 3 agent() calls' in _ctx(proc), _ctx(proc)


def test_a_model_set_to_undefined_is_not_a_routing_decision():
    script = "await agent('x', { model: undefined, effort: 'low' })\n"
    with tempfile.TemporaryDirectory() as d:
        proc = run_hook(Path(d), tool_name='Workflow', tool_input={'script': script})
        assert '1 of 1 agent() calls' in _ctx(proc)


if __name__ == '__main__':
    test_it_fires_at_the_spawn_with_no_env_set()
    test_the_opt_out_silences_it()
    test_a_spawn_that_already_names_a_model_is_left_alone()
    test_a_fan_out_is_reminded_once_not_once_per_agent()
    test_a_different_session_gets_its_own_hint()
    test_the_batch_counter_rule_travels_with_the_hint()
    test_it_never_decides_the_permission()
    test_a_tool_that_is_not_a_spawn_surface_is_silent()
    test_every_failure_path_exits_zero_and_says_nothing()
    test_the_payload_is_ascii_for_a_codepage_limited_console()
    test_a_workflow_whose_every_agent_call_names_a_model_is_left_alone()
    test_a_workflow_with_one_agent_call_that_names_no_model_fires()
    test_an_agent_spawn_without_a_model_still_fires()
    test_a_workflow_script_is_read_from_script_path_relative_to_cwd()
    test_a_workflow_it_cannot_read_fails_toward_the_hint()
    test_a_regex_literal_holding_a_quote_does_not_break_the_parse()
    test_shared_options_resolve_through_a_const_and_a_spread()
    test_options_built_by_a_route_helper_count_as_routed()
    test_a_model_set_to_undefined_is_not_a_routing_decision()
    print('ok: all inject_spawn_routing tests passed')

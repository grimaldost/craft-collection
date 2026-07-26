"""Tests for render.py -- report derivation, the drift gate, and the chain walk (section 3).

Runnable with pytest or `python test_render.py`. PyYAML is a hard dependency (report
derivation parses nested YAML), so this module refuses to run -- and never emits the
`skip:` sentinel -- when PyYAML is absent, keeping the mechanism spine from going
green-via-skip.
"""

from __future__ import annotations

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only on a broken toolchain
    print('FAIL: PyYAML is required for render.py and its tests (mechanism spine must not skip)')
    raise SystemExit(1) from None

import subprocess
import sys
import tempfile
from pathlib import Path

import render

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / 'templates'
PROBE = TEMPLATES / 'probe.yaml'
RG2X2 = HERE.parent / 'examples' / 'rg-2x2' / 'record.yaml'
PAIRED_CONTRAST = HERE / 'fixtures' / 'paired_contrast.yaml'


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding='utf-8'))


# --- canonical serialization ------------------------------------------------


def test_canonical_sorts_keys_and_uses_lf():
    text = render.canonical_yaml({'x': 1, 'a': 2, 'm': 3})
    assert '\r' not in text
    assert text.endswith('\n') and not text.endswith('\n\n')
    order = [line.split(':')[0] for line in text.splitlines()]
    assert order == ['a', 'm', 'x'], order


def test_canonical_float_repr_is_pinned():
    text = render.canonical_yaml({'a': 17.0, 'b': 0.1, 'c': 0.6122})
    assert 'a: 17.0' in text  # repr keeps the trailing .0 (not 17)
    assert 'b: 0.1' in text  # and does not spell 0.1 as 0.10000000000000001
    assert 'c: 0.6122' in text


def test_canonical_is_idempotent():
    data = _load(PROBE)
    once = render.canonical_yaml(data)
    twice = render.canonical_yaml(yaml.safe_load(once))
    assert once == twice


# --- report derivation + parity --------------------------------------------


def test_report_embeds_exactly_one_block_equal_to_record():
    record = _load(PROBE)
    report = render.render_report(record)
    blocks = render._YAML_FENCE.findall(report)
    assert len(blocks) == 1, f'expected one embedded yaml block, got {len(blocks)}'
    embedded = yaml.safe_load(blocks[0])
    # The byte-independent parity half (validate.py's ER-PARITY) re-parses this block;
    # it must equal the record it was derived from.
    assert embedded == record


def test_report_has_lf_and_single_trailing_newline():
    text = render.render_report(_load(PROBE))
    assert '\r' not in text
    assert text.endswith('\n') and not text.endswith('\n\n')


# --- the paired contrast in the derived report (schema v1.1) ----------------


def test_report_carries_the_contrast_and_its_stated_sign_test():
    text = render.render_report(_load(PAIRED_CONTRAST))
    line = next(ln for ln in text.splitlines() if 'with_hint_minus_control' in ln)
    assert 'paired_difference' in line, line
    assert 'estimate=0.2083' in line and 'se=0.1193' in line, line
    assert '6 cluster(s)' in line, line
    assert 'paired_t CI [-0.0984, 0.515]' in line, line
    assert 'sign test p=0.375 on 5 effective cluster(s), 4 positive' in line, line


def test_contrast_line_quotes_the_record_and_never_recomputes():
    # Record-is-source: the renderer reads the stated numbers and validate.py's
    # ER-STATS is what holds them to the clusters block. Were render.py to recompute
    # instead, the prose and the embedded block would be two answers with nothing
    # reconciling them -- so a changed stated value, clusters untouched, must move
    # the line.
    record = _load(PAIRED_CONTRAST)
    record['results']['signal']['contrasts'][0]['sign_test']['p_value'] = 0.01
    line = next(
        ln for ln in render.render_report(record).splitlines() if 'with_hint_minus_control' in ln
    )
    assert 'sign test p=0.01' in line, line


def test_per_arm_interval_is_marked_descriptive_beside_a_contrast():
    record = _load(PAIRED_CONTRAST)
    text = render.render_report(record)
    arm_line = next(ln for ln in text.splitlines() if 'signal / with_hint:' in ln)
    assert 'wilson CI [0.5083, 0.8509] (descriptive' in arm_line, arm_line
    # Without a contrast the same arm line carries no demotion: the marker tracks
    # the presence of a headline on the paired scale, not the arm.
    del record['results']['signal']['contrasts']
    plain = render.render_report(record)
    plain_line = next(ln for ln in plain.splitlines() if 'signal / with_hint:' in ln)
    assert 'descriptive' not in plain_line, plain_line


def test_contrast_reporting_does_not_disturb_the_embedded_block():
    # The contrast lines are derived prose; the drift digest reads only the embedded
    # YAML block, which must still equal the record exactly.
    record = _load(PAIRED_CONTRAST)
    blocks = render._YAML_FENCE.findall(render.render_report(record))
    assert len(blocks) == 1
    assert yaml.safe_load(blocks[0]) == record


# --- the derived sections (section 6) ---------------------------------------
#
# The drift gate digests the embedded YAML alone, so a section the renderer does not
# emit is a silent gap rather than a red gate. These are the sections the acceptance
# criterion names, tested on the shapes a finalized record actually carries.


def _finalized_shape() -> dict:
    """The paired-contrast fixture grown into the shape a finalized record has: a labeled
    contrast row, the 2x2 breakdown, the descriptive tax and a selected interpretation."""
    record = _load(PAIRED_CONTRAST)
    contrast = record['results']['signal']['contrasts'][0]
    contrast['role'] = 'confirmatory'
    record['results']['signal']['contrasts'].append(
        {
            **dict(contrast),
            'name': 'aa_calibration',
            'role': 'exploratory',
            'note': 'A/A calibration -- the instrument noise floor',
        }
    )
    record['analysis_plan'] = {
        'primary_contrast': {'name': 'with_hint_minus_control', 'outcome': 'signal'},
        'decision_rule': {'threshold': 0.15},
    }
    # A pair-scoped block: it lives under its own key and DECLARES which outcome it speaks
    # for, which is how the primary-precision line and the table's grouping still resolve.
    record['results']['signal__aa'] = {
        'outcome': 'signal',
        'class_scope': 'genuine',
        'clusters': record['results']['signal']['clusters'],
        'contrasts': [record['results']['signal']['contrasts'].pop(1)],
    }
    record['state_breakdown'] = {
        'arms': {
            'with_hint': {
                'all': {
                    'scored': 24,
                    'both': 17,
                    'line_only': 3,
                    'skeleton_only': 1,
                    'neither': 3,
                    'line_only_rate': 0.125,
                }
            }
        }
    }
    record['run_economy'] = {
        'per_arm': {
            'with_hint': {
                'runs': 24,
                'mean_turns': 3.5,
                'total_cost_usd': 2.4,
                'mean_cost_usd': 0.1,
            }
        }
    }
    record['conclusion'] = {
        'interpretation': 'content_carries',
        'condition': 'the treated arm moves and the inert arm does not',
        'read': 'the content carries the effect',
        'basis': 'with_hint_minus_control = 0.2083 [-0.0984, 0.515]',
        'rollout_precondition': 'live-hook delivery is unmeasured here',
    }
    return record


def test_the_derived_sections_carry_the_table_precision_states_tax_and_leg():
    text = render.render_report(_finalized_shape())
    assert '## Contrasts (paired, on the clustered scale)' in text
    row = next(ln for ln in text.splitlines() if '| with_hint_minus_control |' in ln)
    # Quoted, never recomputed: the estimate, the interval and the sign test as stated.
    assert '| 0.2083 |' in row and '[-0.0984, 0.515]' in row
    assert 'p=0.375, 4/5 positive' in row
    # The achieved precision is the stated interval's half-width, named against the MEWD.
    assert (
        '- Achieved precision (clustered scale): signal / with_hint_minus_control +/- 0.3067'
        in text
    )
    assert 'declared MEWD 0.15' in text
    # The A/A row labels itself the noise floor; the renderer quotes the label.
    aa = next(ln for ln in text.splitlines() if '| aa_calibration |' in ln)
    assert 'A/A calibration -- the instrument noise floor' in aa
    # The pair-scoped block DECLARES its outcome, so the table groups by the outcome and
    # not by the key the block happens to live under.
    assert aa.startswith('| signal | genuine |'), aa
    assert '## 2x2 states by arm (the line-only rate is first-class)' in text
    assert '| with_hint | all | 24 | 17 | 3 | 1 | 3 | 0.125 |' in text
    assert '## Turn and cost tax (descriptive)' in text
    assert '| with_hint | 24 | 3.5 | 2.4 | 0.1 |' in text
    assert 'Selected: `content_carries`' in text
    assert 'Precondition for any production rollout of a row: live-hook delivery' in text
    # Still exactly one embedded block, still equal to the record.
    blocks = render._YAML_FENCE.findall(text)
    assert len(blocks) == 1 and yaml.safe_load(blocks[0]) == _finalized_shape()


def test_the_new_sections_degrade_to_nothing_without_their_blocks():
    """A record with no contrasts renders no empty scaffolding -- one shared renderer
    serves every tier, so an absent block must produce absence, not a header over a
    header row."""
    text = render.render_report(_load(PROBE))
    for heading in ('## Contrasts', '## 2x2 states', '## Turn and cost tax', '## Interpretation'):
        assert heading not in text, heading
    # The RG-2x2 fixture has contrasts nowhere either, and its committed pair stays clean.
    rg = render.render_report(_load(RG2X2), RG2X2)
    assert '## Contrasts' not in rg
    assert render.check_drift(RG2X2) is None


def test_the_report_opens_with_the_generated_activation_line():
    """Section 3's generator, not a typed string: the line names the record's own tier and
    path, so it cannot drift from the artifact. Without a path there is nothing to name and
    the report opens with its title instead."""
    text = render.render_report(_load(RG2X2), RG2X2)
    assert text.splitlines()[0] == render.record_activation_line(RG2X2)
    assert text.splitlines()[0].startswith('[experiment-rigor | measurement -> ')
    assert text.splitlines()[2].startswith('# Experiment:')
    assert render.render_report(_load(RG2X2)).splitlines()[0].startswith('# Experiment:')


def test_a_tier0_record_gets_no_activation_line():
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / 'record.yaml'
        rec.write_text(
            'schema_version: 1\ntier: check\nexperiment: x\n', encoding='utf-8', newline='\n'
        )
        text = render.render_report(_load(rec), rec)
        assert text.splitlines()[0].startswith('# Experiment:'), text.splitlines()[0]


# --- the drift gate ---------------------------------------------------------


def test_check_clean_render_has_no_drift():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        rec = d / 'record.yaml'
        rec.write_text(PROBE.read_text(encoding='utf-8'), encoding='utf-8')
        (d / 'report.md').write_text(render.render_report(_load(rec)), encoding='utf-8')
        assert render.check_drift(rec) is None


def test_check_detects_a_tampered_value():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        rec = d / 'record.yaml'
        rec.write_text(PROBE.read_text(encoding='utf-8'), encoding='utf-8')
        report = render.render_report(_load(rec))
        (d / 'report.md').write_text(
            report.replace('numerator: 9', 'numerator: 7'), encoding='utf-8'
        )
        assert render.check_drift(rec) is not None


def test_check_ignores_a_cosmetic_prose_edit():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        rec = d / 'record.yaml'
        rec.write_text(PROBE.read_text(encoding='utf-8'), encoding='utf-8')
        report = render.render_report(_load(rec))
        edited = report.replace('do not hand-edit', 'prose changed, semantics intact')
        (d / 'report.md').write_text(edited, encoding='utf-8')
        assert render.check_drift(rec) is None


def test_check_reports_missing_report_as_drift():
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / 'record.yaml'
        rec.write_text(PROBE.read_text(encoding='utf-8'), encoding='utf-8')
        assert render.check_drift(rec) is not None


def test_resolve_pair_from_either_member():
    # F3: either member of the travelling pair resolves to the same (record, report).
    rec, rep = render.resolve_pair('examples/x/report.md')
    assert rec.name == 'record.yaml' and rep.name == 'report.md'
    rec2, rep2 = render.resolve_pair('examples/x/record.yaml')
    assert rec2.name == 'record.yaml' and rep2.name == 'report.md'
    assert rec == rec2 and rep == rep2


def test_check_from_report_path_detects_the_same_drift():
    # F3: invoking --check with the report.md member (record.yaml unrestaged) detects
    # the same drift as invoking it with the record.yaml member.
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        rec = d / 'record.yaml'
        rec.write_text(PROBE.read_text(encoding='utf-8'), encoding='utf-8')
        report = d / 'report.md'
        report.write_text(render.render_report(_load(rec)), encoding='utf-8')
        assert render.check_drift(report) is None
        assert render.check_drift(rec) is None
        report.write_text(
            render.render_report(_load(rec)).replace('numerator: 9', 'numerator: 1'),
            encoding='utf-8',
        )
        assert render.check_drift(report) is not None
        assert render.check_drift(rec) is not None


def test_check_report_without_record_is_drift():
    # F3: a staged report.md with no record.yaml beside it cannot be verified -> drift.
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / 'report.md'
        report.write_text('# orphan\n\n```yaml\ntier: probe\n```\n', encoding='utf-8')
        assert render.check_drift(report) is not None


def test_cli_check_exit_codes():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        rec = d / 'record.yaml'
        rec.write_text(PROBE.read_text(encoding='utf-8'), encoding='utf-8')
        (d / 'report.md').write_text(render.render_report(_load(rec)), encoding='utf-8')
        clean = subprocess.run(  # noqa: S603 - fixed argv
            [sys.executable, str(HERE / 'render.py'), '--check', str(rec)],
            capture_output=True,
            text=True,
        )
        assert clean.returncode == 0, clean.stdout + clean.stderr
        (d / 'report.md').write_text(
            render.render_report(_load(rec)).replace('numerator: 9', 'numerator: 5'),
            encoding='utf-8',
        )
        drift = subprocess.run(  # noqa: S603 - fixed argv
            [sys.executable, str(HERE / 'render.py'), '--check', str(rec)],
            capture_output=True,
            text=True,
        )
        assert drift.returncode == 1, drift.stdout + drift.stderr
        assert 'DRIFT' in drift.stdout


# --- the update chain -------------------------------------------------------


def _min_record(experiment: str, tier: str = 'measurement') -> dict:
    return {'schema_version': 1, 'tier': tier, 'experiment': experiment}


def test_chain_walks_two_node_lineage_root_first():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / 'node-a').mkdir()
        (root / 'node-b').mkdir()
        node_a = _min_record('rg-2x2-measurement', 'measurement')
        (root / 'node-a' / 'record.yaml').write_text(yaml.safe_dump(node_a), encoding='utf-8')
        node_b = _min_record('rg-2x2-decision', 'decision')
        node_b['updates'] = {
            'certainty': 'moderate',
            'downgrade_reasons': ['nondeterminism'],
            'prior': {'source_id': '../node-a/record.yaml'},
        }
        b_path = root / 'node-b' / 'record.yaml'
        b_path.write_text(yaml.safe_dump(node_b), encoding='utf-8')

        chain = render.walk_chain(b_path)
        assert [n['record']['experiment'] for n in chain] == [
            'rg-2x2-measurement',
            'rg-2x2-decision',
        ], chain
        assert all(n['resolved'] for n in chain)

        view = render.render_chain(b_path)
        assert view.index('rg-2x2-measurement') < view.index('rg-2x2-decision')
        assert 'certainty=moderate' in view


def test_chain_marks_an_unresolvable_link():
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        rec = _min_record('orphan', 'decision')
        rec['updates'] = {'prior': {'source_id': 'does-not-exist.yaml'}}
        path = d / 'record.yaml'
        path.write_text(yaml.safe_dump(rec), encoding='utf-8')
        chain = render.walk_chain(path)
        assert any(not n['resolved'] for n in chain), chain


# --- the mantis journal envelope emit (--emit-journal) ----------------------


def test_cli_emit_journal_primary_and_strict():
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / 'record.yaml'
        rec.write_text(PROBE.read_text(encoding='utf-8'), encoding='utf-8')
        primary = subprocess.run(  # noqa: S603 - fixed argv
            [sys.executable, str(HERE / 'render.py'), '--emit-journal', str(rec)],
            capture_output=True,
            text=True,
        )
        assert primary.returncode == 0, primary.stderr
        assert '--- ENTRY_START ---' in primary.stdout and '--- ENTRY_END ---' in primary.stdout
        assert 'record_sha256:' in primary.stdout
        strict = subprocess.run(  # noqa: S603 - fixed argv
            [sys.executable, str(HERE / 'render.py'), '--emit-journal', '--strict', str(rec)],
            capture_output=True,
            text=True,
        )
        assert strict.returncode == 0, strict.stderr
        # The strict fallback drops the provenance superset but keeps the hash-pinned link.
        assert 'experiment:' not in strict.stdout and 'record_ref:' in strict.stdout


# --- the activation line ----------------------------------------------------


def test_activation_line_names_the_records_tier_and_path():
    line = render.record_activation_line(RG2X2)
    assert line.startswith('[experiment-rigor | measurement -> '), line
    assert line.endswith('examples/rg-2x2/record.yaml]'), line
    assert line.isascii(), line  # the generated form carries no glyph (ASCII ratchet)
    artifact = render._ACTIVATION_RE.match(line)['artifact']
    assert '\\' not in artifact, artifact  # POSIX separators, stable across machines
    # The path is not decoration and not machine-local: it is exactly this record's
    # path relative to the repository root. Asserted as a string, since joining an
    # ABSOLUTE artifact to the root would silently discard the root (pathlib) and let
    # the CWD-relative fallback pass this test.
    root = render._repo_root(RG2X2.parent)
    assert root is not None
    assert not Path(artifact).is_absolute(), artifact
    assert artifact == RG2X2.relative_to(root).as_posix(), artifact


def test_check_activation_line_accepts_the_generated_line():
    assert render.check_activation_line(render.record_activation_line(RG2X2), RG2X2) is None


def test_check_activation_line_rejects_a_disagreeing_tier():
    line = render.record_activation_line(RG2X2).replace('measurement', 'probe')
    reason = render.check_activation_line(line, RG2X2)
    assert reason is not None and 'tier' in reason, reason


def test_check_activation_line_rejects_a_disagreeing_path():
    line = render.activation_line('measurement', 'evals/experiments/other/record.yaml')
    reason = render.check_activation_line(line, RG2X2)
    assert reason is not None and 'artifact' in reason, reason


def test_check_activation_line_rejects_a_line_that_is_not_one():
    assert render.check_activation_line('experiment-rigor: measurement', RG2X2) is not None


def test_check_activation_line_reports_a_windows_spelled_path():
    # The comparison is exact: a backslash spelling of the right file is a
    # disagreement, and it is reported as one (naming both spellings) rather than
    # falling through to a bare repr mismatch.
    posix = render.artifact_ref(RG2X2)
    reason = render.check_activation_line(
        render.activation_line('measurement', posix.replace('/', '\\')), RG2X2
    )
    assert reason is not None
    assert reason.startswith('artifact '), reason
    assert posix in reason, reason  # the record's canonical spelling
    assert repr(posix.replace('/', '\\')) in reason, reason  # and the pasted one


def test_activation_line_refuses_a_tier0_check_record():
    # `check` names no artifact and never appears as a tier: value; the generator
    # refuses rather than inventing a path for it.
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / 'record.yaml'
        rec.write_text('schema_version: 1\ntier: check\nexperiment: x\n', encoding='utf-8')
        try:
            render.record_activation_line(rec)
        except ValueError as exc:
            assert 'inline' in str(exc), exc
        else:
            raise AssertionError('a tier-0 `check` record must not yield a generated line')


def test_activation_line_round_trips_outside_a_repository():
    # Outside a checkout there is no root to anchor to: the line names the resolved
    # ABSOLUTE path (so it round-trips from any working directory) and says so on
    # stderr. Under a repo-hosted temp dir the in-repo branch is taken instead, and
    # only the round trip is asserted.
    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / 'record.yaml'
        rec.write_text(PROBE.read_text(encoding='utf-8'), encoding='utf-8')
        line = render.record_activation_line(rec)
        assert '| probe -> ' in line, line
        assert render.check_activation_line(line, rec) is None
        if render._repo_root(rec.resolve().parent) is None:
            artifact = render._ACTIVATION_RE.match(line)['artifact']
            assert Path(artifact).is_absolute(), artifact
            assert artifact == rec.resolve().as_posix(), artifact
            # Invoked from the record's own directory, by its bare relative name: the
            # line must still be the same one (a CWD- or spelling-dependent artifact
            # would make a line generated here read as drifted from anywhere else).
            note = subprocess.run(  # noqa: S603 - fixed argv
                [sys.executable, str(HERE / 'render.py'), '--activation-line', 'record.yaml'],
                capture_output=True,
                text=True,
                cwd=td,
            )
            assert note.returncode == 0, note.stderr
            assert 'outside a git repository' in note.stderr, note.stderr
            assert note.stdout.strip() == line, note.stdout


def test_cli_activation_line_exit_codes_both_directions():
    generated = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, str(HERE / 'render.py'), '--activation-line', str(RG2X2)],
        capture_output=True,
        text=True,
    )
    assert generated.returncode == 0, generated.stderr
    line = generated.stdout.strip()
    assert line == render.record_activation_line(RG2X2), line
    agrees = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, str(HERE / 'render.py'), '--check-activation-line', line, str(RG2X2)],
        capture_output=True,
        text=True,
    )
    assert agrees.returncode == 0, agrees.stdout + agrees.stderr
    for drifted in (
        line.replace('measurement', 'decision'),
        render.activation_line('measurement', 'examples/elsewhere/record.yaml'),
    ):
        proc = subprocess.run(  # noqa: S603 - fixed argv
            [
                sys.executable,
                str(HERE / 'render.py'),
                '--check-activation-line',
                drifted,
                str(RG2X2),
            ],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1, drifted + proc.stdout + proc.stderr
        assert 'MISMATCH' in proc.stdout, proc.stdout


def test_cli_check_activation_line_survives_cp1252_stdout():
    # A hand-written format-(b) line (glyph prefix, middot, arrow) is exactly the
    # non-ASCII input the checker must reject *with its message*. Under a cp1252
    # stdout -- the ordinary Windows default -- printing it used to raise
    # UnicodeEncodeError, so the exit 1 was a crash rather than the verdict.
    import os

    glyph_line = '◇ experiment-rigor · measurement → examples/rg-2x2/record.yaml'
    proc = subprocess.run(  # noqa: S603 - fixed argv
        [
            sys.executable,
            str(HERE / 'render.py'),
            '--check-activation-line',
            glyph_line,
            str(RG2X2),
        ],
        capture_output=True,
        env={**os.environ, 'PYTHONIOENCODING': 'cp1252'},
        encoding='utf-8',
        errors='replace',
    )
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert 'MISMATCH' in proc.stdout, proc.stdout + proc.stderr
    assert 'Traceback' not in proc.stderr, proc.stderr


def test_cli_activation_line_reports_a_bad_record_without_a_traceback():
    # F5: an unreadable record and a tier-0 record are reported like --check reports
    # DRIFT -- one ERROR line, exit 1 -- not as a raw traceback.
    missing = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, str(HERE / 'render.py'), '--activation-line', 'no-such-record.yaml'],
        capture_output=True,
        text=True,
    )
    assert missing.returncode == 1, missing.stdout + missing.stderr
    assert missing.stdout.startswith('ERROR '), missing.stdout
    assert 'Traceback' not in missing.stderr, missing.stderr

    with tempfile.TemporaryDirectory() as td:
        rec = Path(td) / 'record.yaml'
        rec.write_text('schema_version: 1\ntier: check\nexperiment: x\n', encoding='utf-8')
        tier0 = subprocess.run(  # noqa: S603 - fixed argv
            [sys.executable, str(HERE / 'render.py'), '--activation-line', str(rec)],
            capture_output=True,
            text=True,
        )
        assert tier0.returncode == 1, tier0.stdout + tier0.stderr
        assert tier0.stdout.startswith('ERROR ') and 'inline' in tier0.stdout, tier0.stdout
        assert 'Traceback' not in tier0.stderr, tier0.stderr


if __name__ == '__main__':
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
            except Exception as exc:  # report any failure; never emit the ok: sentinel
                failed += 1
                print(f'FAIL {name}: {exc!r}')
    if failed:
        print(f'{failed} test(s) failed')
        sys.exit(1)
    print('ok: all render tests passed')

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

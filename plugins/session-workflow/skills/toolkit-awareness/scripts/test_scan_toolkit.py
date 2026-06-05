"""Tests for scan_toolkit.

Runnable with pytest OR directly: `python test_scan_toolkit.py` (no pytest
dependency required, so the script ships self-verifiable).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scan_toolkit import _plugins_from_json, _read_frontmatter, scan


def _make_tree(root: Path) -> None:
    (root / ".claude/skills/foo").mkdir(parents=True)
    (root / ".claude/skills/foo/SKILL.md").write_text(
        "---\nname: foo\ndescription: Does the foo thing for tests.\n---\nbody\n",
        encoding="utf-8",
    )
    (root / ".claude/commands").mkdir(parents=True)
    (root / ".claude/commands/bar.md").write_text("# bar\n", encoding="utf-8")
    (root / ".claude/agents").mkdir(parents=True)
    (root / ".claude/agents/baz.md").write_text(
        "---\nname: baz\n---\n", encoding="utf-8"
    )
    (root / ".claude/hooks").mkdir(parents=True)
    (root / ".claude/hooks/hook.py").write_text("# hook\n", encoding="utf-8")


def test_scan_enumerates_components():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_tree(root)
        out = scan([root])
        assert "foo" in {s["name"] for s in out["skills"]}
        assert any("foo thing" in s["description"] for s in out["skills"])
        assert "bar" in {c["name"] for c in out["commands"]}
        assert "baz" in {a["name"] for a in out["agents"]}
        assert "hook.py" in {h["name"] for h in out["hooks"]}


def test_missing_dirs_do_not_raise():
    with tempfile.TemporaryDirectory() as d:
        out = scan([Path(d)])  # no .claude at all
        for kind in ("skills", "commands", "agents", "hooks"):
            assert out[kind] == []
        assert "plugins" in out  # CLI-sourced, environment-dependent — just present


def test_plugins_from_json_uses_id_and_hides_enabled():
    # `claude plugin list --json` returns id-keyed objects with no name; derive the
    # name from id and never leak the raw `enabled` bool into the label.
    rows = _plugins_from_json(
        [
            {
                "id": "engineering-discipline@craft-collection",
                "version": "0.1.0",
                "enabled": True,
            },
            {
                "id": "example-tool@example-marketplace",
                "version": "0.3.0",
                "enabled": False,
            },
        ]
    )
    assert rows[0]["name"] == "engineering-discipline (0.1.0)"  # not '? (0.1.0, True)'
    assert rows[1]["name"] == "example-tool (0.3.0, disabled)"
    assert all("?" not in r["name"] and "True" not in r["name"] for r in rows)


def test_read_frontmatter_handles_folded_scalar():
    # A `description: >` folded block must be captured in full, not truncated to ">".
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "SKILL.md"
        p.write_text(
            "---\nname: folded\ndescription: >\n  First line of the\n"
            "  folded description.\nuser-invocable: true\n---\nbody\n",
            encoding="utf-8",
        )
        fm = _read_frontmatter(p)
        assert fm["name"] == "folded"
        assert fm["description"] == "First line of the folded description."
        assert fm["user-invocable"] == "true"


if __name__ == "__main__":
    test_scan_enumerates_components()
    test_missing_dirs_do_not_raise()
    test_plugins_from_json_uses_id_and_hides_enabled()
    test_read_frontmatter_handles_folded_scalar()
    print("ok: all scan_toolkit tests passed")

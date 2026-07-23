"""Tests for scan_toolkit.

Runnable with pytest OR directly: `python test_scan_toolkit.py` (no pytest
dependency required, so the script ships self-verifiable).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from scan_toolkit import (
    _enumerate_plugin_components,
    _merge_skew,
    _plugins_from_json,
    _read_frontmatter,
    _source_manifest_version,
    scan,
)


def _make_tree(root: Path) -> None:
    (root / '.claude/skills/foo').mkdir(parents=True)
    (root / '.claude/skills/foo/SKILL.md').write_text(
        '---\nname: foo\ndescription: Does the foo thing for tests.\n---\nbody\n',
        encoding='utf-8',
    )
    (root / '.claude/commands').mkdir(parents=True)
    (root / '.claude/commands/bar.md').write_text('# bar\n', encoding='utf-8')
    (root / '.claude/agents').mkdir(parents=True)
    (root / '.claude/agents/baz.md').write_text('---\nname: baz\n---\n', encoding='utf-8')
    (root / '.claude/hooks').mkdir(parents=True)
    (root / '.claude/hooks/hook.py').write_text('# hook\n', encoding='utf-8')


def test_scan_enumerates_components():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        _make_tree(root)
        out = scan([root])
        assert 'foo' in {s['name'] for s in out['skills']}
        assert any('foo thing' in s['description'] for s in out['skills'])
        assert 'bar' in {c['name'] for c in out['commands']}
        assert 'baz' in {a['name'] for a in out['agents']}
        assert 'hook.py' in {h['name'] for h in out['hooks']}


def test_frontmatter_quotes_stripped():
    # A YAML-quoted name/description must not render with literal quotes in the
    # inventory. A matched surrounding pair is stripped and \" unescaped; the
    # single-quoted style unescapes '' to '.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        sk = root / '.claude/skills/q'
        sk.mkdir(parents=True)
        (sk / 'SKILL.md').write_text(
            '---\nname: "q"\ndescription: "Says \\"hi\\" politely."\n---\nbody\n',
            encoding='utf-8',
        )
        sk2 = root / '.claude/skills/r'
        sk2.mkdir(parents=True)
        (sk2 / 'SKILL.md').write_text(
            "---\nname: 'r'\ndescription: 'It''s quoted.'\n---\nbody\n",
            encoding='utf-8',
        )
        out = scan([root])
    skills = {s['name']: s for s in out['skills'] if 'plugin' not in s}
    assert 'q' in skills and 'r' in skills, sorted(skills)
    assert skills['q']['description'] == 'Says "hi" politely.'
    assert skills['r']['description'] == "It's quoted."


def test_missing_dirs_do_not_raise():
    with tempfile.TemporaryDirectory() as d:
        out = scan([Path(d)])  # no .claude at all
        # The .claude-dir scan contributes nothing (those items are untagged); any items
        # present come from installed plugins (tagged with a `plugin` key), which are
        # CLI-sourced and environment-dependent, so we don't assert on their count.
        for kind in ('skills', 'commands', 'agents', 'hooks'):
            assert [it for it in out[kind] if 'plugin' not in it] == []
        assert 'plugins' in out  # CLI-sourced, environment-dependent — just present


def test_plugins_from_json_uses_id_and_hides_enabled():
    # `claude plugin list --json` returns id-keyed objects with no name; derive the
    # name from id and never leak the raw `enabled` bool into the label.
    rows = _plugins_from_json(
        [
            {
                'id': 'engineering-discipline@craft-collection',
                'version': '0.1.0',
                'enabled': True,
            },
            {
                'id': 'example-tool@example-marketplace',
                'version': '0.3.0',
                'enabled': False,
            },
        ]
    )
    assert rows[0]['name'] == 'engineering-discipline (0.1.0)'  # not '? (0.1.0, True)'
    assert rows[1]['name'] == 'example-tool (0.3.0, disabled)'
    assert all('?' not in r['name'] and 'True' not in r['name'] for r in rows)


def _make_plugin(install_path: Path) -> None:
    """A fake installed plugin's on-disk layout under its installPath: a skill, a
    command, an agent, and a hooks.json — the components `claude plugin list` points
    at via installPath but never enumerates itself."""
    (install_path / 'skills/foo').mkdir(parents=True)
    (install_path / 'skills/foo/SKILL.md').write_text(
        '---\nname: foo\ndescription: The plugin foo skill.\n---\nbody\n',
        encoding='utf-8',
    )
    (install_path / 'commands').mkdir(parents=True)
    (install_path / 'commands/pcmd.md').write_text('# pcmd\n', encoding='utf-8')
    (install_path / 'agents').mkdir(parents=True)
    (install_path / 'agents/pagent.md').write_text('---\nname: pagent\n---\n', encoding='utf-8')
    (install_path / 'hooks').mkdir(parents=True)
    (install_path / 'hooks/hooks.json').write_text(
        '{"hooks": {"SessionStart": [{"hooks": [{"type": "command"}]}]}}',
        encoding='utf-8',
    )


def test_enumerate_plugin_components_walks_install_path():
    # The core regression: a plugin's installPath must be walked so its skills,
    # commands, agents, and hooks are surfaced (not the blind SKILLS(2)/HOOKS(0)).
    with tempfile.TemporaryDirectory() as d:
        ip = Path(d) / 'plug'
        _make_plugin(ip)
        comps = _enumerate_plugin_components('myplugin', str(ip))
        assert 'foo' in {s['name'] for s in comps['skills']}
        assert all(s['plugin'] == 'myplugin' for s in comps['skills'])
        assert 'pcmd' in {c['name'] for c in comps['commands']}
        assert 'pagent' in {a['name'] for a in comps['agents']}
        # hooks.json events are enumerated (SessionStart), not left at 0
        assert any('SessionStart' in h['name'] for h in comps['hooks'])
        assert all(h['plugin'] == 'myplugin' for h in comps['hooks'])


def test_enumerate_plugin_components_missing_path_is_empty():
    # An installPath that does not resolve yields empty lists, never raises.
    comps = _enumerate_plugin_components('gone', str(Path('does') / 'not' / 'exist'))
    assert comps == {'skills': [], 'commands': [], 'agents': [], 'hooks': []}
    assert _enumerate_plugin_components('none', None) == {
        'skills': [],
        'commands': [],
        'agents': [],
        'hooks': [],
    }


def _make_marketplace(root: Path, plugin: str, version: str) -> Path:
    """A fake marketplace source tree: `.claude-plugin/marketplace.json` declaring
    one plugin whose manifest carries `version` — the shape `claude plugin
    marketplace list` points at via installLocation."""
    import json

    mp = root / 'market'
    (mp / '.claude-plugin').mkdir(parents=True)
    (mp / '.claude-plugin' / 'marketplace.json').write_text(
        json.dumps(
            {'name': 'market', 'plugins': [{'name': plugin, 'source': f'./plugins/{plugin}'}]}
        ),
        encoding='utf-8',
    )
    man = mp / 'plugins' / plugin / '.claude-plugin'
    man.mkdir(parents=True)
    (man / 'plugin.json').write_text(
        json.dumps({'name': plugin, 'version': version}), encoding='utf-8'
    )
    return mp


def test_plugins_from_json_exposes_version_and_marketplace():
    # The skew check needs the raw version and the marketplace half of the id as
    # structured fields, not just baked into the display name.
    rows = _plugins_from_json([{'id': 'plug@market', 'version': '0.1.0', 'enabled': True}])
    assert rows[0]['version'] == '0.1.0'
    assert rows[0]['marketplace'] == 'market'


def test_source_manifest_version_via_marketplace_json():
    with tempfile.TemporaryDirectory() as d:
        mp = _make_marketplace(Path(d), 'plug', '0.2.0')
        assert _source_manifest_version(mp, 'plug') == '0.2.0'


def test_source_manifest_version_fallback_layout():
    # Without a marketplace.json, the conventional plugins/<name>/ layout still resolves.
    with tempfile.TemporaryDirectory() as d:
        mp = _make_marketplace(Path(d), 'plug', '0.3.0')
        (mp / '.claude-plugin' / 'marketplace.json').unlink()
        assert _source_manifest_version(mp, 'plug') == '0.3.0'


def test_source_manifest_version_missing_is_none():
    with tempfile.TemporaryDirectory() as d:
        assert _source_manifest_version(Path(d) / 'nope', 'plug') is None


def test_merge_skew_annotates_stale_install():
    # Installed 0.1.0 vs marketplace source 0.2.0: the row gains a structured
    # source_version, a visible name suffix, and the scan a caveat line — the
    # invisible-skew footgun (a stale install once hid an entire skill).
    rows = _plugins_from_json([{'id': 'plug@market', 'version': '0.1.0', 'enabled': True}])
    with tempfile.TemporaryDirectory() as d:
        mp = _make_marketplace(Path(d), 'plug', '0.2.0')
        caveats = _merge_skew(rows, {'market': str(mp)})
    assert rows[0]['source_version'] == '0.2.0'
    assert 'source 0.2.0' in rows[0]['name']
    assert caveats and 'plug' in caveats[0] and '0.2.0' in caveats[0]


def test_merge_skew_equal_or_unknown_is_silent():
    # A matching version or an unresolvable marketplace produces no annotation and
    # no caveat — absence of evidence is not skew.
    rows = _plugins_from_json(
        [
            {'id': 'same@market', 'version': '0.2.0', 'enabled': True},
            {'id': 'ghost@nowhere', 'version': '0.1.0', 'enabled': True},
        ]
    )
    with tempfile.TemporaryDirectory() as d:
        mp = _make_marketplace(Path(d), 'same', '0.2.0')
        caveats = _merge_skew(rows, {'market': str(mp)})
    assert caveats == []
    assert all('source_version' not in r for r in rows)
    assert 'source' not in rows[0]['name']


def test_read_frontmatter_handles_folded_scalar():
    # A `description: >` folded block must be captured in full, not truncated to ">".
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / 'SKILL.md'
        p.write_text(
            '---\nname: folded\ndescription: >\n  First line of the\n'
            '  folded description.\nuser-invocable: true\n---\nbody\n',
            encoding='utf-8',
        )
        fm = _read_frontmatter(p)
        assert fm['name'] == 'folded'
        assert fm['description'] == 'First line of the folded description.'
        assert fm['user-invocable'] == 'true'


def test_utf8_stdout_survives_cp1252_pipe():
    # Piped Windows stdout defaults to cp1252: an em-dash used to come out as a
    # cp1252 byte (mojibake in UTF-8 terminals) and a '→' crashed the script
    # outright (uncaught UnicodeEncodeError, exit 1). The script must emit UTF-8
    # regardless of the platform default; PYTHONIOENCODING reproduces the
    # cp1252 pipe on any platform.
    import os
    import subprocess
    import sys

    script = Path(__file__).resolve().parent / 'scan_toolkit.py'
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        sk = root / '.claude' / 'skills' / 'uni'
        sk.mkdir(parents=True)
        (sk / 'SKILL.md').write_text(
            '---\nname: uni\ndescription: setas — e → aqui.\n---\nbody\n',
            encoding='utf-8',
        )
        env = dict(os.environ)
        env['PYTHONIOENCODING'] = 'cp1252'
        proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(script), '--root', str(root)],
            capture_output=True,
            env=env,
            timeout=120,
        )
    assert proc.returncode == 0, proc.stderr.decode('utf-8', 'replace')
    assert '→'.encode() in proc.stdout
    assert '—'.encode() in proc.stdout


def _git(*args: str, cwd: Path) -> None:
    import subprocess

    from scan_toolkit import _git_env

    subprocess.run(  # noqa: S603 - fixed argv, no shell
        ['git', *args],  # noqa: S607 - git resolved from PATH
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
        env=_git_env(),  # a hook's GIT_DIR would aim these at the outer repo
    )


def test_source_behind_upstream_counts_fetched_not_merged():
    # The skew below _merge_skew's reach: installed == source reads "no skew"
    # while BOTH trail the remote (a 13-commits-behind main once nearly re-ran a
    # whole audit). Build origin + clone, advance origin, fetch in the clone
    # without merging — the checkout is measurably behind its fetched upstream.
    import shutil

    from scan_toolkit import _source_behind_upstream, _stale_checkout_caveats

    if not shutil.which('git'):
        print('skip: git unavailable, behind-upstream test not run')
        return
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        origin, work, src = base / 'origin.git', base / 'work', base / 'src'
        ident = ('-c', 'user.email=t@t', '-c', 'user.name=t')
        _git('init', '--bare', '-b', 'main', str(origin), cwd=base)
        _git('init', '-b', 'main', str(work), cwd=base)
        _git(*ident, 'commit', '--allow-empty', '-m', 'c1', cwd=work)
        _git('remote', 'add', 'origin', str(origin), cwd=work)
        _git('push', '-q', 'origin', 'main', cwd=work)
        _git('clone', '-q', str(origin), str(src), cwd=base)
        assert _source_behind_upstream(src) == 0  # freshly cloned: up to date
        _git(*ident, 'commit', '--allow-empty', '-m', 'c2', cwd=work)
        _git(*ident, 'commit', '--allow-empty', '-m', 'c3', cwd=work)
        _git('push', '-q', 'origin', 'main', cwd=work)
        _git('fetch', '-q', cwd=src)
        assert _source_behind_upstream(src) == 2
        caveats = _stale_checkout_caveats({'market': str(src)})
        assert len(caveats) == 1
        assert '2 commit(s) behind' in caveats[0]
        assert 'market' in caveats[0]


def test_source_behind_upstream_ignores_inherited_git_dir():
    # Regression: under a git hook (pre-push runs the suite) git exports GIT_DIR,
    # which takes precedence over `-C` -- every child git then answers about the
    # OUTER repo. The whole suite failed only inside `git push`, and the staleness
    # check silently read the wrong checkout. Fails without _git_env().
    import os
    import shutil

    from scan_toolkit import _source_behind_upstream

    if not shutil.which('git'):
        print('skip: git unavailable, inherited-GIT_DIR test not run')
        return
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        origin, work, src = base / 'origin.git', base / 'work', base / 'src'
        ident = ('-c', 'user.email=t@t', '-c', 'user.name=t')
        _git('init', '--bare', '-b', 'main', str(origin), cwd=base)
        _git('init', '-b', 'main', str(work), cwd=base)
        _git(*ident, 'commit', '--allow-empty', '-m', 'c1', cwd=work)
        _git('remote', 'add', 'origin', str(origin), cwd=work)
        _git('push', '-q', 'origin', 'main', cwd=work)
        _git('clone', '-q', str(origin), str(src), cwd=base)
        _git(*ident, 'commit', '--allow-empty', '-m', 'c2', cwd=work)
        _git('push', '-q', 'origin', 'main', cwd=work)
        _git('fetch', '-q', cwd=src)

        prior = os.environ.get('GIT_DIR')
        os.environ['GIT_DIR'] = str(work / '.git')  # what a hook leaks in
        try:
            assert _source_behind_upstream(src) == 1
        finally:
            if prior is None:
                os.environ.pop('GIT_DIR', None)
            else:
                os.environ['GIT_DIR'] = prior


def test_source_behind_upstream_none_without_repo_or_upstream():
    # A non-repo location (or one with no upstream) yields None and no caveat —
    # absence of evidence is not staleness.
    from scan_toolkit import _source_behind_upstream, _stale_checkout_caveats

    with tempfile.TemporaryDirectory() as d:
        assert _source_behind_upstream(Path(d)) is None
        assert _stale_checkout_caveats({'m': d}) == []


# --- (a) skill-list skew: source has a skill the install lacks -----------------


def _make_skill_source(base: Path, plugin: str, skills: tuple[str, ...]) -> Path:
    """A marketplace source tree whose plugin dir carries the named skill subdirs
    (each with a SKILL.md) — the shape the skill-list diff compares against."""
    import json

    mp = base / 'market'
    (mp / '.claude-plugin').mkdir(parents=True)
    (mp / '.claude-plugin' / 'marketplace.json').write_text(
        json.dumps(
            {'name': 'market', 'plugins': [{'name': plugin, 'source': f'./plugins/{plugin}'}]}
        ),
        encoding='utf-8',
    )
    src = mp / 'plugins' / plugin
    (src / '.claude-plugin').mkdir(parents=True)
    (src / '.claude-plugin' / 'plugin.json').write_text(
        json.dumps({'name': plugin, 'version': '0.1.0'}), encoding='utf-8'
    )
    for sk in skills:
        (src / 'skills' / sk).mkdir(parents=True)
        (src / 'skills' / sk / 'SKILL.md').write_text(f'---\nname: {sk}\n---\n', encoding='utf-8')
    return mp


def _make_install(base: Path, skills: tuple[str, ...]) -> Path:
    install = base / 'install'
    for sk in skills:
        (install / 'skills' / sk).mkdir(parents=True)
        (install / 'skills' / sk / 'SKILL.md').write_text(
            f'---\nname: {sk}\n---\n', encoding='utf-8'
        )
    return install


def test_skill_list_skew_flags_missing_skill():
    # Source has alpha+beta, the installed copy only alpha: one caveat naming the
    # plugin and the missing skill(s). Extra-in-installed is never flagged.
    from scan_toolkit import _skill_list_skew

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mp = _make_skill_source(base, 'plug', ('alpha', 'beta'))
        install = _make_install(base, ('alpha',))
        rows = [
            {
                'plugin': 'plug',
                'marketplace': 'market',
                'installPath': str(install),
                'version': '0.1.0',
                'name': 'plug (0.1.0)',
            }
        ]
        caveats = _skill_list_skew(rows, {'market': str(mp)})
    assert len(caveats) == 1
    assert 'installed copy lags repo' in caveats[0]
    assert 'plug' in caveats[0]
    assert 'missing skills: beta' in caveats[0]
    assert 'claude plugin update plug' in caveats[0]


def test_skill_list_skew_silent_when_complete_or_unresolvable():
    # Install has every source skill -> no caveat; a row whose marketplace does
    # not resolve is compared against nothing -> no false skew.
    from scan_toolkit import _skill_list_skew

    with tempfile.TemporaryDirectory() as d:
        base = Path(d)
        mp = _make_skill_source(base, 'plug', ('alpha',))
        install = _make_install(base, ('alpha',))
        complete_row = {
            'plugin': 'plug',
            'marketplace': 'market',
            'installPath': str(install),
            'version': '0.1.0',
            'name': 'plug (0.1.0)',
        }
        unresolvable_row = {
            'plugin': 'ghost',
            'marketplace': 'nowhere',
            'installPath': str(install),
            'version': '0.1.0',
            'name': 'ghost (0.1.0)',
        }
        caveats = _skill_list_skew([complete_row, unresolvable_row], {'market': str(mp)})
    assert caveats == []


# --- (b) inventory cache: fingerprint + hit/miss/TTL/corrupt --------------------


def test_fingerprint_changes_when_file_changes():
    # The fingerprint tracks a scan root's settings file by mtime/size; editing it
    # must change the fingerprint so the cache cannot serve a stale inventory.
    import os

    import scan_toolkit as st

    with tempfile.TemporaryDirectory() as d:
        os.environ['CLAUDE_PLUGIN_DATA'] = d
        try:
            root = Path(d)
            (root / '.claude').mkdir(parents=True)
            f = root / '.claude' / 'settings.json'
            f.write_text('{}', encoding='utf-8')
            fp1 = st._fingerprint([root])
            f.write_text('{"changed": true}', encoding='utf-8')
            fp2 = st._fingerprint([root])
        finally:
            os.environ.pop('CLAUDE_PLUGIN_DATA', None)
    assert fp1 != fp2


def _run_session_start_capturing(st, roots, use_cache):
    """Drive _run_session_start with stdout captured and stdin neutralized (empty
    non-tty), so the serving-snapshot check finds no envelope and never blocks."""
    import contextlib
    import io
    import sys

    buf = io.StringIO()
    prior_stdin = sys.stdin
    sys.stdin = io.StringIO('')  # not a tty, empty -> serving check is a no-op
    try:
        with contextlib.redirect_stdout(buf):
            rc = st._run_session_start(roots, use_cache=use_cache)
    finally:
        sys.stdin = prior_stdin
    return rc, buf.getvalue()


def test_cache_hit_prints_cached_text_without_scanning():
    import os

    import scan_toolkit as st

    with tempfile.TemporaryDirectory() as d:
        os.environ['CLAUDE_PLUGIN_DATA'] = d
        try:
            roots = [Path(d)]
            fp = st._fingerprint(roots)
            st._write_cache(fp, 'Installed toolkit: skills: CACHED_MARKER', [])
            calls = []
            orig = st.scan
            st.scan = lambda r: (calls.append(1), {'plugins': [], '_caveats': []})[1]
            try:
                rc, out = _run_session_start_capturing(st, roots, use_cache=True)
            finally:
                st.scan = orig
        finally:
            os.environ.pop('CLAUDE_PLUGIN_DATA', None)
    assert rc == 0
    assert 'CACHED_MARKER' in out
    assert calls == []  # a fresh hit never invokes the scan (nor the claude CLI)


def test_cache_miss_rescans_and_writes():
    import os

    import scan_toolkit as st

    with tempfile.TemporaryDirectory() as d:
        os.environ['CLAUDE_PLUGIN_DATA'] = d
        try:
            roots = [Path(d)]
            calls = []
            orig = st.scan
            st.scan = lambda r: (
                calls.append(1),
                {
                    'skills': [{'name': 'freshfoo'}],
                    'commands': [],
                    'agents': [],
                    'hooks': [],
                    'plugins': [],
                    '_caveats': [],
                },
            )[1]
            try:
                rc, out = _run_session_start_capturing(st, roots, use_cache=True)
            finally:
                st.scan = orig
            wrote = st._read_cache()
        finally:
            os.environ.pop('CLAUDE_PLUGIN_DATA', None)
    assert rc == 0
    assert calls == [1]  # no cache present -> scanned once
    assert 'freshfoo' in out
    assert wrote is not None and 'freshfoo' in wrote.get('output_text', '')


def test_cache_ttl_expiry_rescans():
    import os

    import scan_toolkit as st

    with tempfile.TemporaryDirectory() as d:
        os.environ['CLAUDE_PLUGIN_DATA'] = d
        try:
            roots = [Path(d)]
            fp = st._fingerprint(roots)
            st._write_cache(fp, 'Installed toolkit: skills: STALECACHE', [])
            # Age the record beyond the TTL in place.
            import json

            rec = json.loads(st._cache_path().read_text(encoding='utf-8'))
            rec['ts'] = 0  # epoch: far older than 24h
            st._cache_path().write_text(json.dumps(rec), encoding='utf-8')
            calls = []
            orig = st.scan
            st.scan = lambda r: (
                calls.append(1),
                {
                    'skills': [{'name': 'freshfoo'}],
                    'commands': [],
                    'agents': [],
                    'hooks': [],
                    'plugins': [],
                    '_caveats': [],
                },
            )[1]
            try:
                rc, out = _run_session_start_capturing(st, roots, use_cache=True)
            finally:
                st.scan = orig
        finally:
            os.environ.pop('CLAUDE_PLUGIN_DATA', None)
    assert rc == 0
    assert calls == [1]  # expired -> rescanned
    assert 'STALECACHE' not in out
    assert 'freshfoo' in out


def test_corrupt_cache_read_returns_none_and_rescans():
    import os

    import scan_toolkit as st

    with tempfile.TemporaryDirectory() as d:
        os.environ['CLAUDE_PLUGIN_DATA'] = d
        try:
            cd = st._cache_dir()
            cd.mkdir(parents=True, exist_ok=True)
            st._cache_path().write_text('not valid json {{{', encoding='utf-8')
            assert st._read_cache() is None  # never raises
            roots = [Path(d)]
            calls = []
            orig = st.scan
            st.scan = lambda r: (
                calls.append(1),
                {
                    'skills': [{'name': 'freshfoo'}],
                    'commands': [],
                    'agents': [],
                    'hooks': [],
                    'plugins': [],
                    '_caveats': [],
                },
            )[1]
            try:
                rc, out = _run_session_start_capturing(st, roots, use_cache=True)
            finally:
                st.scan = orig
        finally:
            os.environ.pop('CLAUDE_PLUGIN_DATA', None)
    assert rc == 0
    assert calls == [1]
    assert 'freshfoo' in out


# --- (c) serving-snapshot check: transcript diff vs installed hooks.json --------


def _make_plugin_hooks(install_path: Path, command: str, args: list[str]) -> None:
    import json

    (install_path / 'hooks').mkdir(parents=True)
    (install_path / 'hooks' / 'hooks.json').write_text(
        json.dumps(
            {
                'hooks': {
                    'SessionStart': [
                        {'hooks': [{'type': 'command', 'command': command, 'args': args}]}
                    ]
                }
            }
        ),
        encoding='utf-8',
    )


_UV_ARGS = ['run', '--no-project', '--', 'python', '${CLAUDE_PLUGIN_ROOT}/x.py', '--session-start']
_UV_JOINED = 'uv ' + ' '.join(_UV_ARGS)
_BARE_JOINED = 'python ${CLAUDE_PLUGIN_ROOT}/x.py --session-start'


def test_serving_snapshot_matched_is_silent():
    from scan_toolkit import _serving_snapshot_caveats

    with tempfile.TemporaryDirectory() as d:
        ip = Path(d) / 'plug'
        _make_plugin_hooks(ip, 'uv', _UV_ARGS)
        caveats = _serving_snapshot_caveats([_UV_JOINED], [str(ip)])
    assert caveats == []


def test_serving_snapshot_frozen_bare_python_flags_caveat():
    # The desktop-app freeze signature: the transcript records a bare-python hook
    # command that no installed (uv-style) hooks.json produces -> one caveat.
    from scan_toolkit import _serving_snapshot_caveats

    with tempfile.TemporaryDirectory() as d:
        ip = Path(d) / 'plug'
        _make_plugin_hooks(ip, 'uv', _UV_ARGS)
        caveats = _serving_snapshot_caveats([_BARE_JOINED], [str(ip)])
    assert len(caveats) == 1
    assert 'frozen plugin snapshot' in caveats[0]
    assert 'claude -p' in caveats[0]


def test_serving_snapshot_caps_at_two_lines():
    from scan_toolkit import _serving_snapshot_caveats

    recorded = [
        '${CLAUDE_PLUGIN_ROOT}/one --a',
        '${CLAUDE_PLUGIN_ROOT}/two --b',
        '${CLAUDE_PLUGIN_ROOT}/three --c',
        '${CLAUDE_PLUGIN_ROOT}/one --a',  # duplicate, deduped
    ]
    caveats = _serving_snapshot_caveats(recorded, [])
    assert len(caveats) == 2


def test_transcript_hook_commands_parsing_and_filtering():
    # Only attachment.command strings containing ${CLAUDE_PLUGIN_ROOT} are kept;
    # malformed lines, non-attachment records, and settings-level (no-ROOT) hook
    # commands are skipped without raising.
    import json

    from scan_toolkit import _transcript_hook_commands

    with tempfile.TemporaryDirectory() as d:
        tp = Path(d) / 't.ndjson'
        lines = [
            json.dumps(
                {
                    'attachment': {
                        'type': 'hook_success',
                        'command': 'python ${CLAUDE_PLUGIN_ROOT}/a.py --session-start',
                    },
                    'type': 'attachment',
                }
            ),
            'this is not json at all',
            json.dumps(
                {'attachment': {'command': 'settings-hook --no-root'}, 'type': 'attachment'}
            ),
            json.dumps({'type': 'user', 'message': 'hi'}),
            json.dumps({'attachment': 'not-a-dict'}),
        ]
        tp.write_text('\n'.join(lines), encoding='utf-8')
        cmds = _transcript_hook_commands(str(tp))
    assert cmds == ['python ${CLAUDE_PLUGIN_ROOT}/a.py --session-start']


def test_transcript_missing_is_silent():
    from scan_toolkit import _transcript_hook_commands

    cmds = _transcript_hook_commands(str(Path('does') / 'not' / 'exist.ndjson'))
    assert cmds == []


def test_check_serving_cli_mode_reports_frozen():
    import contextlib
    import io
    import json

    import scan_toolkit as st

    with tempfile.TemporaryDirectory() as d:
        ip = Path(d) / 'plug'
        _make_plugin_hooks(ip, 'uv', _UV_ARGS)
        tp = Path(d) / 't.ndjson'
        tp.write_text(
            json.dumps({'attachment': {'command': _BARE_JOINED}, 'type': 'attachment'}),
            encoding='utf-8',
        )
        orig = st.scan
        st.scan = lambda r: {'plugins': [{'installPath': str(ip)}], '_caveats': []}
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = st.main(['--check-serving', str(tp)])
        finally:
            st.scan = orig
    assert rc == 0
    assert 'frozen plugin snapshot' in buf.getvalue()


def test_check_serving_cli_mode_reports_match():
    import contextlib
    import io
    import json

    import scan_toolkit as st

    with tempfile.TemporaryDirectory() as d:
        ip = Path(d) / 'plug'
        _make_plugin_hooks(ip, 'uv', _UV_ARGS)
        tp = Path(d) / 't.ndjson'
        tp.write_text(
            json.dumps({'attachment': {'command': _UV_JOINED}, 'type': 'attachment'}),
            encoding='utf-8',
        )
        orig = st.scan
        st.scan = lambda r: {'plugins': [{'installPath': str(ip)}], '_caveats': []}
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = st.main(['--check-serving', str(tp)])
        finally:
            st.scan = orig
    assert rc == 0
    assert 'serving snapshot matches installed hooks' in buf.getvalue()


if __name__ == '__main__':
    test_scan_enumerates_components()
    test_frontmatter_quotes_stripped()
    test_missing_dirs_do_not_raise()
    test_plugins_from_json_uses_id_and_hides_enabled()
    test_plugins_from_json_exposes_version_and_marketplace()
    test_source_manifest_version_via_marketplace_json()
    test_source_manifest_version_fallback_layout()
    test_source_manifest_version_missing_is_none()
    test_merge_skew_annotates_stale_install()
    test_merge_skew_equal_or_unknown_is_silent()
    test_enumerate_plugin_components_walks_install_path()
    test_enumerate_plugin_components_missing_path_is_empty()
    test_read_frontmatter_handles_folded_scalar()
    test_utf8_stdout_survives_cp1252_pipe()
    test_source_behind_upstream_counts_fetched_not_merged()
    test_source_behind_upstream_ignores_inherited_git_dir()
    test_source_behind_upstream_none_without_repo_or_upstream()
    test_skill_list_skew_flags_missing_skill()
    test_skill_list_skew_silent_when_complete_or_unresolvable()
    test_fingerprint_changes_when_file_changes()
    test_cache_hit_prints_cached_text_without_scanning()
    test_cache_miss_rescans_and_writes()
    test_cache_ttl_expiry_rescans()
    test_corrupt_cache_read_returns_none_and_rescans()
    test_serving_snapshot_matched_is_silent()
    test_serving_snapshot_frozen_bare_python_flags_caveat()
    test_serving_snapshot_caps_at_two_lines()
    test_transcript_hook_commands_parsing_and_filtering()
    test_transcript_missing_is_silent()
    test_check_serving_cli_mode_reports_frozen()
    test_check_serving_cli_mode_reports_match()
    print('ok: all scan_toolkit tests passed')

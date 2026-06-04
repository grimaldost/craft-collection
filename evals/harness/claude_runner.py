"""Shared agent/judge spawner for the eval harness.

`parse_stream` + `AgentRun` are the pure, unit-tested core; `build_command` is a
pure command assembler (unit-tested); `run_agent` is the subprocess wrapper that
spawns `claude -p`. Isolation is via a copied-credentials temp CLAUDE_CONFIG_DIR
(authenticated but skill-free) — `--bare` is NOT used because it strips the
config-bound subscription login. Stdlib only.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

# stderr signatures that justify a retry (transient server/network failures).
_TRANSIENT = re.compile(
    r'(429|529|overloaded|rate.?limit|\b5\d\d\b|ECONNRESET|ETIMEDOUT|connection reset)',
    re.IGNORECASE,
)


@dataclass
class AgentRun:
    """Parsed result of one headless `claude -p` run."""

    activated_skills: set[str] = field(default_factory=set)
    result_text: str = ''
    cost_usd: float = 0.0
    num_turns: int = 0
    is_error: bool = False
    plugins_loaded: list[str] = field(default_factory=list)
    plugin_errors: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    raw: list = field(default_factory=list)

    def plugin_loaded(self, name: str) -> bool:
        return any(name in p for p in self.plugins_loaded)

    def activated(self, target: str) -> bool:
        return any(target in s for s in self.activated_skills)


def make_isolated_config(real_config: str | None = None) -> str:
    """Create a temp CLAUDE_CONFIG_DIR with the real config's top-level files
    (auth + settings) copied in, but NO plugins/ dir — an authenticated yet
    skill-free baseline. Caller cleans up with `cleanup_dir`.
    """
    real = Path(real_config or (Path.home() / '.claude'))
    dest = Path(tempfile.mkdtemp(prefix='eval_cfg_'))
    for entry in real.iterdir():
        if entry.is_file():
            try:
                shutil.copy2(entry, dest / entry.name)
            except OSError:
                pass  # skip unreadable/locked files; auth file is what matters
    return str(dest)


def cleanup_dir(path: str, attempts: int = 4) -> None:
    """Best-effort recursive delete; tolerates Windows file locks from claude."""
    for _ in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except OSError:
            time.sleep(0.5)


def map_concurrent(items: Iterable, fn, concurrency: int = 4) -> list:
    """Apply `fn` to each item with a bounded thread pool, preserving input order.

    Each `claude -p` spawn is subprocess-bound and releases the GIL while it waits,
    so threads parallelize the agent runs and cut the focused run's wall time
    several-fold. `concurrency <= 1` runs sequentially (used by tests/debugging).
    Transient failures are already absorbed inside `run_agent`, so `fn` should not
    raise; if it does, the exception surfaces when the result list is built.
    """
    items = list(items)
    if concurrency <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        return list(ex.map(fn, items))


def _walk_tool_uses(obj: object) -> Iterator[dict]:
    """Yield every `tool_use` dict nested anywhere inside a message object."""
    if isinstance(obj, dict):
        if obj.get('type') == 'tool_use':
            yield obj
        for v in obj.values():
            yield from _walk_tool_uses(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_tool_uses(v)


def parse_stream(lines: Iterable[str]) -> AgentRun:
    """Parse `--output-format stream-json` NDJSON lines, defensively."""
    run = AgentRun()
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        run.raw.append(obj)
        kind = obj.get('type') if isinstance(obj, dict) else None
        if kind == 'system' and obj.get('subtype') == 'init':
            for plugin in obj.get('plugins') or []:
                name = plugin.get('name') if isinstance(plugin, dict) else str(plugin)
                if name:
                    run.plugins_loaded.append(name)
            run.plugin_errors.extend(obj.get('plugin_errors') or [])
        if kind == 'result':
            run.result_text = obj.get('result') or run.result_text
            run.cost_usd = obj.get('total_cost_usd') or run.cost_usd
            run.num_turns = obj.get('num_turns') or run.num_turns
            run.is_error = bool(obj.get('is_error', run.is_error))
            if isinstance(obj.get('usage'), dict):
                run.usage = obj['usage']
        for tool_use in _walk_tool_uses(obj):
            if tool_use.get('name') == 'Skill':
                inp = tool_use.get('input') or {}
                value = (inp.get('name') or inp.get('skill') or inp.get('command') or ''
                         if isinstance(inp, dict) else str(inp))
                if value:
                    run.activated_skills.add(value)
    return run


def build_command(*, plugin_dir: str | None, allowed_tools: str, model: str,
                  max_turns: int, max_budget_usd: float, stream: bool) -> list[str]:
    """Assemble the `claude -p` argv. Pure — no I/O. No --bare (it strips login);
    isolation comes from a clean CLAUDE_CONFIG_DIR passed to run_agent."""
    cmd = [
        'claude', '-p',
        '--permission-mode', 'bypassPermissions',
        '--no-session-persistence',
        '--model', model,
        '--max-turns', str(max_turns),
        '--allowed-tools', allowed_tools,
    ]
    if max_budget_usd:
        cmd += ['--max-budget-usd', str(max_budget_usd)]
    cmd += (['--output-format', 'stream-json', '--verbose'] if stream
            else ['--output-format', 'json'])
    if plugin_dir:
        cmd += ['--plugin-dir', str(plugin_dir)]
    return cmd


def _parse_proc(stdout: str, stream: bool) -> AgentRun:
    if stream:
        return parse_stream(stdout.splitlines())
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return AgentRun(result_text=stdout)
    return AgentRun(
        result_text=data.get('result') or '',
        cost_usd=data.get('total_cost_usd') or 0.0,
        num_turns=data.get('num_turns') or 0,
        is_error=bool(data.get('is_error', False)),
    )


def run_agent(prompt: str, *, plugin_dir: str | None = None, allowed_tools: str = '',
              model: str = 'claude-sonnet-4-6', max_turns: int = 8,
              max_budget_usd: float = 0.5, timeout: int = 300, stream: bool = True,
              max_attempts: int = 3, config_dir: str | None = None,
              cwd: str | None = None) -> AgentRun:
    """Run one headless `claude -p`, feeding the prompt on stdin. `config_dir`
    sets CLAUDE_CONFIG_DIR (the isolated, authed-but-skill-free config); `cwd`
    sets a neutral working directory. Retries transient failures; never timeouts.
    """
    cmd = build_command(plugin_dir=plugin_dir, allowed_tools=allowed_tools, model=model,
                        max_turns=max_turns, max_budget_usd=max_budget_usd, stream=stream)
    env = os.environ.copy()
    if config_dir:
        env['CLAUDE_CONFIG_DIR'] = config_dir
    last: subprocess.CompletedProcess | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                cmd, input=prompt, capture_output=True, text=True,
                encoding='utf-8', timeout=timeout, env=env, cwd=cwd,
            )
        except subprocess.TimeoutExpired:
            return AgentRun(is_error=True, result_text=f'TIMEOUT after {timeout}s')
        except FileNotFoundError:
            return AgentRun(is_error=True, result_text='claude CLI not found on PATH')
        if proc.returncode == 0:
            return _parse_proc(proc.stdout, stream)
        last = proc
        if attempt < max_attempts and _TRANSIENT.search(proc.stderr or ''):
            time.sleep(min(10 * 2 ** (attempt - 1), 120) + random.uniform(0, 5))  # noqa: S311
            continue
        break
    run = _parse_proc(last.stdout, stream) if last else AgentRun(is_error=True)
    run.is_error = True
    if last and not run.result_text:
        run.result_text = (last.stderr or '')[:500]
    return run

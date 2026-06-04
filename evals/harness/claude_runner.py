"""Shared agent/judge spawner for the eval harness.

`parse_stream` + `AgentRun` are the pure, unit-tested core; `build_command` is a
pure command assembler (unit-tested); `run_agent` is the subprocess wrapper that
spawns `claude -p` (validated by the smoke checks). Stdlib only.
"""

from __future__ import annotations

import json
import random
import re
import subprocess
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

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
    raw: list = field(default_factory=list)

    def plugin_loaded(self, name: str) -> bool:
        return any(name in p for p in self.plugins_loaded)

    def activated(self, target: str) -> bool:
        return any(target in s for s in self.activated_skills)


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
    """Parse `--output-format stream-json` NDJSON lines, defensively.

    Tolerates non-JSON lines and event-shape variation across CLI versions.
    """
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
    """Assemble the `claude -p` argv. Pure — no I/O. Both A/B arms use --bare."""
    cmd = [
        'claude', '-p',
        '--permission-mode', 'bypassPermissions',
        '--no-session-persistence',
        '--bare',
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
              max_budget_usd: float = 0.5, timeout: int = 300,
              stream: bool = True, max_attempts: int = 3) -> AgentRun:
    """Run one headless `claude -p`, feeding the prompt on stdin. Retries transient
    failures with backoff; never retries timeouts. Returns an AgentRun."""
    cmd = build_command(plugin_dir=plugin_dir, allowed_tools=allowed_tools, model=model,
                        max_turns=max_turns, max_budget_usd=max_budget_usd, stream=stream)
    last: subprocess.CompletedProcess | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
                cmd, input=prompt, capture_output=True, text=True,
                encoding='utf-8', timeout=timeout,
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

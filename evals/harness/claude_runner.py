"""Shared agent/judge spawner for the eval harness.

This module starts with the pure, unit-tested stream parser (`parse_stream` +
`AgentRun`); the subprocess `run_agent` is added in Phase 2. Stdlib only.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field


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

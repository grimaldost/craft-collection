"""LLM-as-judge for the eval harness.

Starts with the pure JSON-extraction helper (`extract_verdict`); the
`judge_pointwise` / `judge_pairwise` callers (which spawn `claude -p`) are added
in Phase 4. Stdlib only.
"""

from __future__ import annotations

import json
import re


def extract_verdict(text: str) -> dict | None:
    """Pull a JSON verdict object out of a judge's (messy) text reply.

    Tries a fenced ```json block first, then the first balanced {...} substring.
    Returns the parsed dict, or None if no JSON object is found.
    """
    if not text:
        return None
    fenced = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except (json.JSONDecodeError, ValueError):
            pass
    start = text.find('{')
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break  # not valid JSON; advance to the next '{'
        start = text.find('{', start + 1)
    return None

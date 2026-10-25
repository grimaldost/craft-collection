"""Pending-asks gate: the asks a turn raised reach its final block.

    python final_block_gate.py --prompt-submit   # UserPromptSubmit: a new turn, empty ledger
    python final_block_gate.py --post-tool-use   # PostToolUse on the desktop next-step box tool
    python final_block_gate.py --stop            # Stop: record this stop's asks; advise on dropped ones
    python final_block_gate.py --health          # print the ledgers' counts (no hook input)

Why. Measured on 2026-10-25 over 499 turns of long autonomous sessions: in a
third of the turns that asked the operator for a decision, the ask was first
raised in a message the agent then continued past (a stop that a subagent result
or a notification woke again), and 36% of those asks were absent from the turn's
final block, the only text the operator reads. The loss rose from 2% with no such
stop to 35% with five or more. Prose rules about it were in context the whole
time; this hook is the mechanism.

How. A per-session ledger under the plugin's data directory keeps the asks each
stop's `last_assistant_message` carried (the field the harness fills at Stop, so
nothing here reads the transcript, which may lag). At a stop with nothing in
flight (`background_tasks` empty or absent) whose message does not restate an
earlier ask of the same turn, the hook returns `hookSpecificOutput.additionalContext`
naming the dropped asks verbatim, once per ask, so the model restates each one
with its options and a recommendation or says it is resolved. The desktop app's
next-step box counts as a channel: a PostToolUse hook on its tool records the
box's question. `UserPromptSubmit` empties the ledger: a new human prompt starts
a new turn.

Asks are found lexically (question-mark sentences with a second-person or
permission marker, explicit requests, pending-list markers; Portuguese and
English), which the measurement put at 82% recall. Restatement is a token
overlap, not a judgment: the model does the judging when it reads the advice.

Gate: `SESSION_WORKFLOW_FINAL_BLOCK_GATE`. Unset or any other value: on. `observe`:
the ledger records what it would have advised and the hook prints nothing. `0`:
off, nothing is read or written. Every path exits 0: a hook must not break a
session.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

GATE = 'SESSION_WORKFLOW_FINAL_BLOCK_GATE'
STATE_DIR_ENV = 'SESSION_WORKFLOW_FINAL_BLOCK_GATE_DIR'
BOX_TOOL_SUFFIX = 'wrap_up'
MAX_ASKS = 40
MAX_BOX_ASKS = 8
MAX_EVENTS = 200
MAX_ASKS_PER_MESSAGE = 10

_PT_MARK = re.compile(
    r'(voc[eê]|\bseu\b|\bsua\b|\bquer\b|prefere|\bposso\b|\bdevo\b|podemos|confirma|autoriza|'  # ascii-ok
    r'aprova|\bsigo\b|prossigo|seguimos|avan[cç]o|\bqual\b|\bquais\b|\bok\b|t[aá] bom|'
    r'concorda|libera|\btopa\b|\bo senhor\b|\ba senhora\b)',
    re.I,
)
_EN_MARK = re.compile(
    r'(\byou\b|\byour\b|should i\b|shall i\b|\bwhich\b|\bok\b|\bproceed\b|\bconfirm\b|go ahead|'
    r'want me|would you|do you|can i\b|may i\b)',
    re.I,
)
_IMPERATIVE = re.compile(
    r'(\bme (diga|avise|confirme|responda|mande|passe|d[eê])\b|'  # ascii-ok
    r'\baguardo (o seu|seu|sua|voc[eê]|a sua)\b|\baguardando (o seu|seu|sua|voc[eê])|'
    r'preciso (do|de) (seu|sua|um) (ok|sim|aval|decisão|decisao|resposta)|'
    r'(diga|responda) (sim|não|nao)\b|\b(com|sem) (o )?seu (sim|ok|aval)\b|'
    r'quando voc[eê] (disser|der) (sim|ok|o sinal)|(esperando|esperam|aguardam) (por )?voc[eê]|'
    r'fica (com voc[eê]|a seu crit[eé]rio|na sua mão)|'
    r'se (voc[eê]|o senhor|a senhora) (quiser|concordar|preferir|aprovar|autorizar|disser|topar)|'
    r'let me know|your call|please confirm|awaiting your|waiting (for|on) your|'
    r'need your (ok|decision|answer|approval|go-ahead)|tell me (which|whether|if)|pick one|'
    r'choose (one|between)|say (yes|no|go)\b)',
    re.I,
)
_LIST_MARKER = re.compile(
    r'^\W*((decis(ão|ao|ões|oes)|pend[eê]ncias?|perguntas?|aprova(ç|c)(ão|ao|ões|oes)|'  # ascii-ok
    r'escolhas?)\b[^.\n]{0,60}(\bsuas?\b|pendentes?|em aberto|abertas?|para voc[eê]|esperando|'
    r'aguardando|que destravam)[^.\n]{0,50}:?\W*$'
    r'|(seguem|ficam|estão|estao|continuam?) (esperando|aguardando|pendentes?|abertos?|em aberto|'
    r'com voc[eê])[^.\n]{0,40}:?\W*$'
    r'|(decisions?|pending decisions?|open questions?|approvals? needed|your call|questions? for you|'
    r'decisions? for you)\b[^.\n]{0,60}:?\W*$)',
    re.I,
)
_SENTENCE = re.compile(r'(?<=[.!?])\s+|\n+')
_TOKEN = re.compile(r'[a-zà-ü0-9]{4,}')  # ascii-ok
_STOPWORDS = frozenset(
    [
        'para',
        'voce',
        'você',  # ascii-ok
        'seus',
        'suas',
        'isso',
        'este',
        'esta',
        'essa',
        'esse',
        'aqui',
        'agora',
        'posso',
        'devo',
        'quer',
        'pode',
        'deve',
        'depois',
        'antes',
        'ainda',
        'mesmo',
        'como',
        'quando',
        'onde',
        'porque',
        'tambem',
        'também',  # ascii-ok
        'sobre',
        'entre',
        'pelo',
        'pela',
        'this',
        'that',
        'with',
        'your',
        'yours',
        'should',
        'could',
        'would',
        'want',
        'have',
        'from',
        'into',
        'there',
        'here',
        'then',
        'than',
        'about',
        'which',
        'while',
        'still',
        'just',
        'also',
        'been',
        'were',
        'will',
        'they',
        'them',
        'some',
        'what',
        'when',
        'where',
    ]
)


# ---------------------------------------------------------------- environment


def mode() -> str:
    """off | observe | on. The guard that documents the default: `== '0'` opts out."""
    value = os.environ.get(GATE)
    if value == '0':
        return 'off'
    if value == 'observe':
        return 'observe'
    return 'on'


def _state_dir() -> Path:
    override = os.environ.get(STATE_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get('CLAUDE_PLUGIN_DATA') or tempfile.gettempdir()
    return Path(base) / 'final-block-gate'


def _safe_session(session_id: object) -> str:
    text = str(session_id or 'unknown')
    return re.sub(r'[^A-Za-z0-9._-]', '_', text)[:80]


def ledger_path(session_id: object) -> Path:
    return _state_dir() / f'{_safe_session(session_id)}.json'


def _load_stdin_json() -> dict:
    try:
        raw = sys.stdin.buffer.read().decode('utf-8-sig', errors='replace')
        data = json.loads(raw) if raw.strip() else {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# -------------------------------------------------------------------- ledger


def _empty_ledger(session_id: object) -> dict:
    return {
        'session_id': str(session_id or ''),
        'turn': 0,
        'asks': [],
        'box_asks': [],
        'events': [],
    }


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None


def load_ledger(session_id: object) -> dict:
    data = _read_json(ledger_path(session_id))
    if isinstance(data, dict) and isinstance(data.get('asks'), list):
        data.setdefault('box_asks', [])
        data.setdefault('events', [])
        data.setdefault('turn', 0)
        return data
    return _empty_ledger(session_id)


def save_ledger(session_id: object, ledger: dict) -> None:
    """Whole-file replace through a temp file, so a crash leaves the old ledger, not a half one."""
    path = ledger_path(session_id)
    ledger['asks'] = ledger['asks'][-MAX_ASKS:]
    ledger['box_asks'] = ledger['box_asks'][-MAX_BOX_ASKS:]
    ledger['events'] = ledger['events'][-MAX_EVENTS:]
    with contextlib.suppress(Exception):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f'.{os.getpid()}.tmp')
        tmp.write_text(json.dumps(ledger, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, path)


# ---------------------------------------------------------------- detection


def _strip_code(text: str) -> str:
    out, fence = [], False
    for line in text.split('\n'):
        if line.strip().startswith('```'):
            fence = not fence
            continue
        if fence or line.lstrip().startswith('>') or line.count('|') >= 2:
            continue
        out.append(line)
    return '\n'.join(out)


def ask_sentences(text: str) -> list[str]:
    """Sentences of `text` that ask the operator for a decision, approval, answer or action.

    Waits on subagents, CI or documents ("aguardo o PR13") are not asks: only a wait
    addressed to the reader ("aguardo o seu sim") counts.
    """
    found: list[str] = []
    clean = _strip_code(text or '')
    for line in clean.split('\n'):
        stripped = line.strip()
        if 0 < len(stripped) < 140 and _LIST_MARKER.search(stripped):
            found.append(stripped)
    for sentence in _SENTENCE.split(clean):
        sentence = sentence.strip()
        if len(sentence.split()) < 3:
            continue
        if (
            sentence.endswith('?') and (_PT_MARK.search(sentence) or _EN_MARK.search(sentence))
        ) or _IMPERATIVE.search(sentence):
            found.append(sentence)
    unique: list[str] = []
    for item in found:
        if item not in unique:
            unique.append(item)
    return unique[:MAX_ASKS_PER_MESSAGE]


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall((text or '').lower()) if t not in _STOPWORDS}


def restated(ask: str, text: str) -> bool:
    """True when `text` carries the ask's words again: two of its content tokens (one
    when it has only one), or half of them by Jaccard. A lexical floor, not a judgment."""
    ask_tokens = _content_tokens(ask)
    if not ask_tokens:
        return ask.strip().lower() in (text or '').lower()
    text_tokens = _content_tokens(text)
    shared = len(ask_tokens & text_tokens)
    if shared >= min(2, len(ask_tokens)):
        return True
    return shared / len(ask_tokens | text_tokens) >= 0.5


def _same_ask(a: str, b: str) -> bool:
    return a == b or (restated(a, b) and restated(b, a))


def advice(asks: list[str]) -> str:
    lines = '\n'.join(f'- {a}' for a in asks)
    return (
        'Earlier in this turn you asked the operator something and then continued working. '
        'Your last message does not carry these asks:\n'
        f'{lines}\n'
        'If a decision, approval or action is still owed, restate each one in full in the final '
        'block, with its options and your recommendation; if one is resolved or no longer applies, '
        'say so in one line.'
    )


# ------------------------------------------------------------------ handlers


def handle_prompt_submit(payload: dict) -> int:
    """A new human prompt starts a new turn: the ledger forgets the previous turn's asks."""
    if mode() == 'off':
        return 0
    session_id = payload.get('session_id')
    if not session_id:
        return 0
    ledger = load_ledger(session_id)
    fresh = _empty_ledger(session_id)
    fresh['turn'] = int(ledger.get('turn', 0)) + 1
    fresh['events'] = ledger.get('events', [])[-MAX_EVENTS:]
    save_ledger(session_id, fresh)
    return 0


def handle_post_tool_use(payload: dict) -> int:
    """The desktop next-step box carries a question the operator sees under the final message."""
    if mode() == 'off':
        return 0
    session_id = payload.get('session_id')
    name = str(payload.get('tool_name') or '')
    if not session_id or not name.endswith(BOX_TOOL_SUFFIX):
        return 0
    tool_input = payload.get('tool_input')
    ask = tool_input.get('ask') if isinstance(tool_input, dict) else None
    if not isinstance(ask, str) or not ask.strip():
        return 0
    ledger = load_ledger(session_id)
    ledger['box_asks'].append(ask.strip())
    save_ledger(session_id, ledger)
    return 0


def handle_stop(payload: dict) -> dict | None:
    """Record this stop's asks; advise, once per ask, on earlier asks the message dropped."""
    current_mode = mode()
    if current_mode == 'off':
        return None
    session_id = payload.get('session_id')
    if not session_id:
        return None
    text = payload.get('last_assistant_message')
    text = text if isinstance(text, str) else ''
    ledger = load_ledger(session_id)
    box_asks = list(ledger.get('box_asks', []))
    carried = text if not box_asks else text + '\n' + '\n'.join(box_asks)
    pending = [a for a in ledger['asks'] if not a.get('advised') and not a.get('restated')]
    missing: list[dict] = []
    for ask in pending:
        if restated(ask['text'], carried):
            ask['restated'] = True
        else:
            missing.append(ask)
    tasks = payload.get('background_tasks')
    busy = isinstance(tasks, list) and len(tasks) > 0
    output = None
    now = time.strftime('%Y-%m-%dT%H:%M:%S')
    if text.strip() and missing and not busy:
        for ask in missing:
            ask['advised'] = True
        kind = 'advised' if current_mode == 'on' else 'observed'
        ledger['events'].append({'ts': now, 'kind': kind, 'n': len(missing)})
        if current_mode == 'on':
            output = {
                'hookSpecificOutput': {
                    'hookEventName': 'Stop',
                    'additionalContext': advice([a['text'] for a in missing]),
                }
            }
    for sentence in ask_sentences(text):
        if not any(_same_ask(sentence, a['text']) for a in ledger['asks']):
            ledger['asks'].append(
                {'text': sentence, 'ts': now, 'advised': False, 'restated': False}
            )
    ledger['box_asks'] = []
    save_ledger(session_id, ledger)
    return output


def health() -> str:
    """One line per ledger: turns, asks recorded, advised, observed."""
    lines = []
    for path in sorted(_state_dir().glob('*.json')):
        data = _read_json(path)
        if not isinstance(data, dict):
            continue
        events = data.get('events', [])
        advised = sum(int(e.get('n', 0)) for e in events if e.get('kind') == 'advised')
        observed = sum(int(e.get('n', 0)) for e in events if e.get('kind') == 'observed')
        lines.append(
            f'{path.stem}: turn {data.get("turn", 0)}, asks {len(data.get("asks", []))}, '
            f'advised {advised}, observed {observed}'
        )
    return '\n'.join(lines) if lines else f'no ledgers under {_state_dir()}'


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if '--health' in argv:
            print(health())
            return 0
        payload = _load_stdin_json()
        if '--prompt-submit' in argv:
            return handle_prompt_submit(payload)
        if '--post-tool-use' in argv:
            return handle_post_tool_use(payload)
        if '--stop' in argv:
            output = handle_stop(payload)
            if output is not None:
                print(json.dumps(output, ensure_ascii=False))
            return 0
        print('usage: final_block_gate.py --prompt-submit | --post-tool-use | --stop | --health')
        return 0
    except Exception:
        return 0


if __name__ == '__main__':
    sys.exit(main())

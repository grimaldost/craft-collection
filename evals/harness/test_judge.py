"""Tests for judge.extract_verdict. Runnable with pytest or `python test_judge.py`."""

from __future__ import annotations

from judge import extract_verdict


def test_extracts_fenced_json():
    txt = 'Here is my assessment:\n```json\n{"score":0.8,"pass":true,"reason":"ok"}\n```\n'
    v = extract_verdict(txt)
    assert v['score'] == 0.8 and v['pass'] is True


def test_extracts_bare_json_object():
    v = extract_verdict('prose {"score": 0.4, "pass": false, "reason": "x"} more')
    assert v['pass'] is False


def test_returns_none_on_no_json():
    assert extract_verdict('no json here') is None


if __name__ == '__main__':
    test_extracts_fenced_json()
    test_extracts_bare_json_object()
    test_returns_none_on_no_json()
    print('ok: all judge extract tests passed')

"""Word-level comparison for dictation practice.

Case and punctuation are ignored so the diff reports what was heard, not
typing style. Contractions keep their apostrophe as part of the word.
"""
from __future__ import annotations
import difflib
import re

_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*|\d+(?:[.,]\d+)*")


def tokens(text: str) -> list[str]:
    return [word.replace("'", "") for word in _WORD.findall(text.lower().replace("’", "'"))]


def compare(expected: str, typed: str) -> dict:
    """Align typed words against the expected sentence.

    Returns the expected tokens with per-word status ('ok', 'wrong',
    'missing'), typed tokens with no counterpart ('extra'), and the share of
    expected tokens typed correctly ('accuracy', 0..1).
    """
    exp, typ = tokens(expected), tokens(typed)
    statuses = ['missing'] * len(exp)
    extras: list[str] = []
    matcher = difflib.SequenceMatcher(None, exp, typ, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for offset in range(i2 - i1):
                statuses[i1 + offset] = 'ok'
        elif tag == 'delete':
            for offset in range(i1, i2):
                statuses[offset] = 'missing'
        else:
            for offset in range(i1, i2):
                statuses[offset] = 'wrong'
            extras.extend(typ[j1:j2])
    ok = statuses.count('ok')
    return {'expected': exp, 'statuses': statuses, 'extra': extras,
            'accuracy': round(ok / len(exp), 4) if exp else 1.0}

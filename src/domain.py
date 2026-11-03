from __future__ import annotations

import re


WORD_PATTERN = re.compile(r"[A-Za-z]+(?:(?:['’][A-Za-z]+)|(?:-[A-Za-z]+))*\Z")


def normalize_line_endings(text: str) -> str:
    """Convert Windows and legacy line endings to the one Qt expects."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_article_text(text: str) -> str:
    """Normalize line endings while preserving paragraph spacing."""
    return normalize_line_endings(text).strip()


def python_offset_to_qt(text: str, offset: int) -> int:
    """Convert a Python character offset to Qt's UTF-16 document position."""
    return len(text[:offset].encode("utf-16-le")) // 2


def qt_offset_to_python(text: str, offset: int) -> int:
    """Convert a Qt UTF-16 document position to a Python character offset."""
    consumed = 0
    for index, character in enumerate(text):
        if consumed >= offset:
            return index
        consumed += len(character.encode("utf-16-le")) // 2
    return len(text)


def find_selected_word(text: str, start: int, end: int) -> tuple[int, int, str] | None:
    """Return the exact selected English word range, if the selection is one word."""
    if start < 0 or end > len(text) or start >= end:
        return None
    selected = text[start:end]
    if not WORD_PATTERN.fullmatch(selected):
        return None
    if start > 0 and (text[start - 1].isalpha() or text[start - 1] in "'’-"):
        return None
    if end < len(text) and (text[end].isalpha() or text[end] in "'’-"):
        return None
    return start, end, selected


def sentence_for_range(text: str, start: int, end: int) -> str:
    """Return the sentence containing a text range for vocabulary context."""
    left = max(text.rfind(mark, 0, start) for mark in ".!?\n")
    right_candidates = [text.find(mark, end) for mark in ".!?\n"]
    right_candidates = [position for position in right_candidates if position >= 0]
    right = min(right_candidates) + 1 if right_candidates else len(text)
    return text[left + 1 : right].strip()



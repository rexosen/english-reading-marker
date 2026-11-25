"""Vocabulary-book categories.

One category per word. A word's category is resolved as:

1. a manual assignment stored in ``study_items`` (key ``vcat:<word>``), which wins;
2. otherwise the category derived from the article the word was underlined in — the
   title prefix (``听力:`` / ``阅读:`` / ``Listening:`` / ``Reading:``) first, then the
   article's own group name, so a re-imported or renamed article re-classifies itself
   without any bookkeeping.

Only manual assignments are persisted, and they live in ``study_items``, so phones and
desktops share them through the existing ``study`` sync channel without a schema change.
``vgroup:auto:reading`` and ``vgroup:auto:listening`` are built-in and never stored.
"""
from __future__ import annotations

import re
import uuid
from urllib.parse import quote, unquote

AUTO_READING = 'vgroup:auto:reading'
AUTO_LISTENING = 'vgroup:auto:listening'
AUTO_CATEGORIES = ((AUTO_LISTENING, '听力'), (AUTO_READING, '阅读'))
AUTO_NAMES = dict(AUTO_CATEGORIES)
GROUP_PREFIX = 'vgroup:'
WORD_PREFIX = 'vcat:'

# Title prefixes used by the reading/listening libraries (half- and full-width colon).
TITLE_PATTERN = re.compile(r'^\s*(听力|阅读|listening|reading)\s*[:：]', re.IGNORECASE)
NAME_TO_AUTO = {name.lower(): key for key, name in AUTO_CATEGORIES}
NAME_TO_AUTO.update({'听力': AUTO_LISTENING, '阅读': AUTO_READING,
                     'listening': AUTO_LISTENING, 'reading': AUTO_READING})


def word_key(word: str) -> str:
    """Study-record key of a word, case and spacing insensitive."""
    return WORD_PREFIX + quote(str(word).strip().casefold(), safe='')


def word_of_key(key: str) -> str:
    return unquote(key[len(WORD_PREFIX):]) if key.startswith(WORD_PREFIX) else ''


def category_from_title(title: str) -> str:
    match = TITLE_PATTERN.match(title or '')
    if not match:
        return ''
    return NAME_TO_AUTO.get(match.group(1).lower(), '')


def category_from_name(name: str) -> str:
    """Built-in key when a group/category name means 听力 or 阅读, else the name itself."""
    return NAME_TO_AUTO.get(normalize_name(name), normalize_name(name))


def normalize_name(name: str) -> str:
    """Comparison key for category names: spacing is noise (“必 背” is “必背”)."""
    return re.sub(r"\s+", "", str(name or "")).casefold()


def display_name(name: str) -> str:
    return " ".join(str(name or "").split())


class VocabularyCategories:
    def __init__(self, study):
        self.study = study

    # ---- categories -------------------------------------------------------------
    def custom(self) -> dict[str, str]:
        items = self.study.items()
        return {key: value['name'] for key, value in items.items()
                if key.startswith(GROUP_PREFIX) and value and key not in AUTO_NAMES}

    def all(self) -> dict[str, str]:
        result = dict(AUTO_NAMES)
        result.update(self.custom())
        return result

    def name(self, key: str) -> str:
        return self.all().get(key, '')

    def create(self, name: str) -> str:
        name = display_name(name)
        if not name:
            raise ValueError('分类名称不能为空。')
        existing = self.find_by_name(name)
        if existing:
            return existing
        key = GROUP_PREFIX + str(uuid.uuid4())
        self.study.set(key, {'name': name})
        return key

    def rename(self, key: str, name: str) -> None:
        if key in AUTO_NAMES:
            raise ValueError('“听力”和“阅读”是内置分类，不能改名。')
        name = display_name(name)
        if not name:
            raise ValueError('分类名称不能为空。')
        duplicate = self.find_by_name(name)
        if duplicate and duplicate != key:
            raise ValueError('已存在同名分类，请换一个名称。')
        self.study.set(key, {'name': name})

    def delete(self, key: str) -> None:
        if key in AUTO_NAMES:
            raise ValueError('“听力”和“阅读”是内置分类，不能删除。')
        self.study.set(key, None)
        for word, group in list(self.every_assignment().items()):
            if group == key:
                self.study.set(word_key(word), None)

    def find_by_name(self, name: str) -> str:
        wanted = normalize_name(name)
        for key, existing in self.all().items():
            if normalize_name(existing) == wanted:
                return key
        return ''

    # ---- word assignments -------------------------------------------------------
    def every_assignment(self) -> dict[str, str]:
        """Every stored word -> category record, including ones whose category is gone."""
        return {word_of_key(key): (value or {}).get('group', '')
                for key, value in self.study.items().items() if key.startswith(WORD_PREFIX) and value}

    def assignments(self) -> dict[str, str]:
        """Manually assigned word -> category key, ignoring stale records."""
        categories = self.all()
        return {word: group for word, group in self.every_assignment().items() if group in categories}

    def manual(self, word: str) -> str:
        return self.assignments().get(str(word).strip().casefold(), '')

    def assign(self, word: str, category: str) -> None:
        word = str(word).strip()
        if not word:
            raise ValueError('请先选中一个生词。')
        key = word_key(word)
        if not category:
            self.study.set(key, None)
            return
        if category not in self.all():
            raise ValueError('分类不存在，请重新选择。')
        self.study.set(key, {'word': word, 'group': category})

    def _resolve(self, assignments: dict[str, str], word: str, title: str, group_name: str) -> str:
        assigned = assignments.get(str(word).strip().casefold(), '')
        if assigned:
            return assigned
        derived = category_from_title(title) or category_from_name(group_name)
        return derived if derived in AUTO_NAMES else ''

    def resolve(self, word: str, title: str = '', group_name: str = '') -> str:
        """Category key of a word: manual assignment wins, else the article decides."""
        return self._resolve(self.assignments(), word, title, group_name)

    def annotate(self, records, article_info) -> list[dict]:
        """Attach ``category`` (key) and ``category_name`` to every vocabulary record."""
        assignments = self.assignments()
        result = []
        for record in records:
            info = article_info.get(record['article_id'], {})
            key = self._resolve(assignments, record['word'], info.get('title', ''), info.get('group', ''))
            result.append({**record, 'category': key, 'category_name': self.name(key)})
        return result

"""Shared learning records. Null values are retained as sync tombstones."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
import re
import uuid


def initialize_study(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS study_items(key TEXT PRIMARY KEY,value TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
    CREATE TRIGGER IF NOT EXISTS study_added AFTER INSERT ON study_items BEGIN INSERT INTO sync_journal(kind) VALUES('study'); END;
    CREATE TRIGGER IF NOT EXISTS study_changed AFTER UPDATE ON study_items BEGIN INSERT INTO sync_journal(kind) VALUES('study'); END;
    ''')


def study_snapshot(db):
    return {row['key']: json.loads(row['value']) for row in db.execute('SELECT key,value FROM study_items')}


_UNSPECIFIED = object()

def _review_schedule(value):
    """Validate a review grade and return (grade, due, interval, count)."""
    if value.get('grade') not in ('again', 'hard', 'known'):
        raise ValueError('复习评分无效')
    try:
        parsed = datetime.fromisoformat(value['due'].replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            raise ValueError()
        interval = float(value['interval'])
        if not 0 <= interval <= 365:
            raise ValueError()
        count = int(value.get('count', 1))
        if not 1 <= count <= 100000:
            raise ValueError()
    except (ValueError, KeyError, TypeError, OverflowError):
        raise ValueError('复习时间或间隔无效')
    return value['grade'], parsed.isoformat(), interval, count


def set_study(db, key, value, *, expected=_UNSPECIFIED):
    if not isinstance(key, str) or len(key) > 220 or not re.fullmatch(r'(group|meta|note|review|vgroup|vcat|listen):[A-Za-z0-9:_~.%-]+', key):
        raise ValueError('学习记录编号无效')
    prefix = key.split(':', 1)[0]
    if value is None:
        if prefix not in ('note', 'group', 'vgroup', 'vcat', 'listen'):
            raise ValueError('此类学习记录不能删除')
    else:
        if not isinstance(value, dict) or len(json.dumps(value, ensure_ascii=False)) > 40000:
            raise ValueError('学习记录格式无效或过长')
        if prefix in ('group', 'vgroup'):
            value = {'name': _text(value.get('name'), 60)}
            for other in db.execute("SELECT key,value FROM study_items WHERE key LIKE ? AND key!=?", (prefix + ':%', key)):
                existing = json.loads(other['value'])
                if existing and existing['name'].casefold() == value['name'].casefold():
                    raise ValueError('已存在同名分组，请选择现有分组或换一个名称')
        elif prefix == 'vcat':
            # Vocabulary-book category: one record per word, no article binding, so the
            # same word keeps its category wherever it was underlined.
            from src.vocabulary import AUTO_NAMES, GROUP_PREFIX
            word = _text(value.get('word'), 100)
            group = value.get('group', '')
            if not isinstance(group, str):
                raise ValueError('生词分类无效')
            if group not in AUTO_NAMES:
                stored = {row[0] for row in db.execute("SELECT key FROM study_items WHERE key LIKE ?", (GROUP_PREFIX + '%',))}
                if group not in stored:
                    raise ValueError('生词分类不存在，请重新选择')
            value = {'word': word, 'group': group}
        elif prefix == 'listen':
            article_id = key.split(':', 1)[1]
            row = db.execute('SELECT 1 FROM sync_articles WHERE sync_id=?', (article_id,)).fetchone()
            if row is None:
                raise ValueError('听力标记对应文章不存在')
            cleaned = {}
            for span_key, item in value.items():
                if not isinstance(item, dict) or item.get('status') not in ('heard', 'missed'):
                    continue
                if type(item.get('start')) is not int or type(item.get('end')) is not int:
                    continue
                cleaned[str(span_key)] = {
                    'start': item['start'],
                    'end': item['end'],
                    'text': str(item.get('text', ''))[:4000],
                    'status': item['status'],
                    'updated': str(item.get('updated', '')),
                }
            value = cleaned
        elif prefix == 'review' and key.startswith('review:manual:'):
            # Review record of a hand-written word or phrase: keyed by vocabulary id.
            try:
                vocabulary_id = int(key.split(':', 2)[2])
            except (ValueError, IndexError):
                raise ValueError('复习记录编号无效')
            if not db.execute('SELECT 1 FROM vocabulary WHERE id=? AND article_id IS NULL', (vocabulary_id,)).fetchone():
                raise ValueError('复习记录没有对应的自建词条')
            grade, due, interval, count = _review_schedule(value)
            value = {'manual': True, 'vocabulary_id': vocabulary_id, 'grade': grade,
                     'due': due, 'interval': interval, 'count': count}
        else:
            article_id = value.get('article_id')
            row = db.execute('SELECT a.* FROM articles a JOIN sync_articles s ON a.id=s.article_id WHERE s.sync_id=?', (article_id,)).fetchone()
            if row is None:
                raise ValueError('学习记录对应文章不存在')
            if prefix == 'meta':
                if key != 'meta:' + article_id:
                    raise ValueError('文章分类编号不匹配')
                group = value.get('group', '')
                if not isinstance(group, str) or len(group) > 100:
                    raise ValueError('分组编号无效')
                value = {'article_id': article_id, 'group': group, 'pinned': bool(value.get('pinned')), 'read': bool(value.get('read'))}
            else:
                start, end = value.get('start'), value.get('end')
                if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(row['text']):
                    raise ValueError('学习记录位置无效')
                if prefix == 'note':
                    if value.get('text') != row['text'][start:end]:
                        raise ValueError('收藏内容与原文位置不符')
                    value = {'article_id': article_id, 'start': start, 'end': end, 'text': row['text'][start:end],
                             'translation': _text(value.get('translation', ''), 20000, empty=True), 'note': _text(value.get('note', ''), 10000, empty=True)}
                else:
                    if key != f'review:{article_id}:{start}:{end}' or not db.execute('SELECT 1 FROM vocabulary WHERE article_id=? AND start=? AND end=?', (row['id'], start, end)).fetchone():
                        raise ValueError('复习记录没有对应的生词')
                    grade, due, interval, count = _review_schedule(value)
                    value = {'article_id': article_id, 'start': start, 'end': end, 'grade': grade, 'due': due, 'interval': interval, 'count': count}
    if prefix == 'note' and expected is not _UNSPECIFIED:
        current = db.execute('SELECT value FROM study_items WHERE key=?', (key,)).fetchone()
        current = json.loads(current[0]) if current else None
        if current != expected and current != value:
            if value is not None:
                # Keep both edits instead of replacing a note changed elsewhere.
                key = 'note:' + str(uuid.uuid4())
            elif current is not None:
                set_study(db, 'note:' + str(uuid.uuid4()), current)
    db.execute('INSERT INTO study_items(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,version=study_items.version+1', (key, json.dumps(value, ensure_ascii=False)))
    return key


def _text(value, limit, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError('内容为空或超过长度限制')
    return value.strip()


def sentence_ranges(text):
    """Return codepoint ranges, preserving exact punctuation and paragraph offsets."""
    ranges, start = [], 0
    abbreviations = {'mr', 'mrs', 'ms', 'dr', 'prof', 'st', 'vs', 'etc', 'e.g', 'i.e'}
    for match in re.finditer(r'[.!?。！？]+[”’\"\']*|\n+', text):
        boundary = match.end()
        punctuation = match.group()
        if punctuation.startswith('.'):
            prefix = text[start:match.start()]
            token = re.search(r'([A-Za-z.]+)$', prefix)
            if (token and (token.group(1).lower() in abbreviations or len(token.group(1)) == 1)) or (match.start() > 0 and boundary < len(text) and text[match.start()-1].isdigit() and text[boundary].isdigit()):
                continue
        if boundary < len(text) and not text[boundary].isspace() and text[boundary] not in '。！？':
            continue
        left, right = start, boundary
        while left < right and text[left].isspace(): left += 1
        while right > left and text[right-1].isspace(): right -= 1
        if right > left: ranges.append((left, right, text[left:right]))
        start = boundary
    left = start
    while left < len(text) and text[left].isspace(): left += 1
    if left < len(text): ranges.append((left, len(text.rstrip()), text[left:].rstrip()))
    return ranges


class StudyRepository:
    def __init__(self, repository):
        self.repository = repository
        self.db = repository.connection

    def items(self):
        return study_snapshot(self.db)

    def set(self, key, value, *, expected=_UNSPECIFIED):
        with self.db:
            return set_study(self.db, key, value, expected=expected)

    def sync_id(self, article_id):
        return self.db.execute('SELECT sync_id FROM sync_articles WHERE article_id=?', (article_id,)).fetchone()[0]

    def metadata(self, article_id):
        sync_id = self.sync_id(article_id)
        return self.items().get('meta:' + sync_id) or {'article_id': sync_id, 'group': '', 'pinned': False, 'read': False}

    def update_metadata(self, article_id, **fields):
        meta = self.metadata(article_id)
        self.set('meta:' + meta['article_id'], {**meta, **fields})

    def groups(self):
        return {key: value['name'] for key, value in self.items().items() if key.startswith('group:') and value}

    def save_note(self, article_id, start, end, translation='', note='', key=None, expected=_UNSPECIFIED):
        article = self.repository.get_article(article_id)
        key = key or 'note:' + str(uuid.uuid4())
        return self.set(key, {'article_id': self.sync_id(article_id), 'start': start, 'end': end, 'text': article['text'][start:end], 'translation': translation, 'note': note}, expected=expected)

    def notes(self):
        by_sync = {self.sync_id(a['id']): a for a in self.repository.list_articles()}
        return [{'key': key, '_base': value, **value, 'local_id': by_sync[value['article_id']]['id'], 'title': by_sync[value['article_id']]['title']}
                for key, value in self.items().items() if key.startswith('note:') and value and value['article_id'] in by_sync]

    def review_cards(self, *, all_cards=False, category=None, article_info=None):
        items, now, cards = self.items(), datetime.now(timezone.utc), []
        vocab_list = self.repository.list_vocabulary()
        if category not in (None, 'all'):
            from src.vocabulary import VocabularyCategories
            annotated = VocabularyCategories(self).annotate(vocab_list, article_info or {})
            vocab_list = [w for w in annotated if w['category'] == category]
        for word in vocab_list:
            if word['article_id'] is None:
                # Hand-written entry: reviewed under its own vocabulary id.
                key = f"review:manual:{word['id']}"
            else:
                key = f"review:{self.sync_id(word['article_id'])}:{word['start']}:{word['end']}"
            record = items.get(key)
            if all_cards or not record or datetime.fromisoformat(record['due']) <= now:
                cards.append({**word, 'key': key, 'record': record,
                              'sync_id': None if word['article_id'] is None else self.sync_id(word['article_id'])})
        return sorted(cards, key=lambda card: (card['record'] or {}).get('due', ''))

    def grade(self, card, grade):
        previous = self.items().get(card['key']) or {}
        interval = 0 if grade == 'again' else 1 if grade == 'hard' else min(365, max(3, previous.get('interval', 0) * 2))
        due = datetime.now(timezone.utc) + (timedelta(minutes=10) if grade == 'again' else timedelta(days=interval))
        schedule = {'grade': grade, 'due': due.isoformat(), 'interval': interval, 'count': previous.get('count', 0) + 1}
        if card['article_id'] is None:
            self.set(card['key'], {'manual': True, 'vocabulary_id': card['id'], **schedule})
            return
        self.set(card['key'], {'article_id': card['sync_id'], 'start': card['start'], 'end': card['end'], **schedule})

    def stats(self, *, article_info=None, listening=None) -> dict:
        articles = self.repository.list_articles()
        items = self.items()
        sync_ids = dict(self.db.execute('SELECT article_id, sync_id FROM sync_articles'))
        read_articles = sum(
            1 for a in articles if (items.get('meta:' + sync_ids.get(a['id'], '')) or {}).get('read')
        )
        total_words = sum(len(re.findall(r"[A-Za-z0-9'-]+", a['text'])) for a in articles)
        total_annotations = self.db.execute('SELECT COUNT(*) FROM annotations').fetchone()[0]
        vocab = self.repository.list_vocabulary()
        now = datetime.now(timezone.utc)
        due_vocab = 0
        mastered_vocab = 0
        total_reviews = 0
        for w in vocab:
            key = f"review:manual:{w['id']}" if w['article_id'] is None else f"review:{sync_ids.get(w['article_id'], '')}:{w['start']}:{w['end']}"
            rec = items.get(key)
            if not rec or datetime.fromisoformat(rec['due']) <= now:
                due_vocab += 1
            if rec:
                total_reviews += int(rec.get('count', 0))
                if float(rec.get('interval', 0)) >= 7:
                    mastered_vocab += 1
        from src.vocabulary import VocabularyCategories
        cats = VocabularyCategories(self)
        annotated = cats.annotate(vocab, article_info or {})
        cat_counts: dict[str, int] = {}
        for rec in annotated:
            label = rec['category_name'] or '未分类'
            cat_counts[label] = cat_counts.get(label, 0) + 1
        dictation = listening.dictation_summary() if listening and hasattr(listening, 'dictation_summary') else {'sessions': 0, 'avg_accuracy': 0.0}
        return {
            'total_articles': len(articles),
            'read_articles': read_articles,
            'total_words': total_words,
            'total_annotations': total_annotations,
            'total_notes': len(self.notes()),
            'total_vocab': len(vocab),
            'due_vocab': due_vocab,
            'mastered_vocab': mastered_vocab,
            'total_reviews': total_reviews,
            'category_counts': sorted(cat_counts.items(), key=lambda kv: -kv[1]),
            'dictation_sessions': dictation['sessions'],
            'dictation_avg_accuracy': dictation['avg_accuracy'],
        }

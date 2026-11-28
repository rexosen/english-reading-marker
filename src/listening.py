"""Listening self-assessment marks and dictation session history.

Marks bind to an article sync id plus sentence range and text; a mark whose
stored text no longer matches the article is treated as absent, so edits drop
stale marks without deleting data. When attached to a StudyRepository, marks
are also mirrored to ``study_items`` (``listen:<sync_id>``) so they sync across
devices automatically.
"""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ('heard', 'missed')
_DICTATION_KEY = '__dictation_history__'


class ListeningReviews:
    def __init__(self, path, study=None):
        self.path = Path(path)
        self.study = study
        self._data = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(loaded, dict):
                    self._data = loaded
            except (ValueError, OSError):
                self._data = {}
        self.pull_from_study()

    def pull_from_study(self) -> None:
        """Merge synced listening marks from study_items into local cache."""
        if self.study is None:
            return
        try:
            items = self.study.items()
        except Exception:
            return
        changed = False
        for key, value in items.items():
            if not key.startswith('listen:') or not isinstance(value, dict):
                continue
            article_id = key[len('listen:'):]
            local = self._data.setdefault(article_id, {})
            for span_key, rec in value.items():
                if not isinstance(rec, dict):
                    continue
                cur = local.get(span_key)
                if cur is None or str(rec.get('updated', '')) > str(cur.get('updated', '')):
                    local[span_key] = rec
                    changed = True
        if changed:
            self._save()

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=self.path.parent, suffix='.tmp', delete=False) as handle:
            json.dump(self._data, handle, ensure_ascii=False)
            temporary = Path(handle.name)
        try:
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

    def mark(self, article_id, start, end, text, status):
        """Set 'heard'/'missed' for a sentence, or clear the mark for None."""
        if status not in STATUSES + (None,):
            raise ValueError('自评状态无效')
        records = self._data.setdefault(article_id, {})
        key = f'{start}:{end}'
        if status is None:
            records.pop(key, None)
        else:
            records[key] = {'start': start, 'end': end, 'text': text, 'status': status,
                            'updated': datetime.now(timezone.utc).isoformat()}
        self._save()
        if self.study is not None:
            try:
                self.study.set(f'listen:{article_id}', records if records else None)
            except Exception:
                pass

    def status(self, article_id, start, end, text):
        record = self._data.get(article_id, {}).get(f'{start}:{end}')
        return record['status'] if record and record['text'] == text else None

    def missed(self, article_id, sentences):
        """Sentences of this article marked 'missed' and still matching the text."""
        current = {(start, end): text for start, end, text in sentences}
        result = []
        for record in self._data.get(article_id, {}).values():
            if not isinstance(record, dict):
                continue
            span = (record['start'], record['end'])
            if record.get('status') == 'missed' and current.get(span) == record.get('text'):
                result.append((span[0], span[1], record['text']))
        return sorted(result)

    def record_dictation(self, article_id: str, sentence_count: int, avg_accuracy: float) -> None:
        if sentence_count <= 0:
            return
        history = self._data.setdefault(_DICTATION_KEY, [])
        if not isinstance(history, list):
            history = []
            self._data[_DICTATION_KEY] = history
        history.append({
            'article_id': article_id,
            'sentences': int(sentence_count),
            'accuracy': round(float(avg_accuracy), 4),
            'at': datetime.now(timezone.utc).isoformat(),
        })
        if len(history) > 200:
            del history[:-200]
        self._save()

    def dictation_summary(self) -> dict:
        history = self._data.get(_DICTATION_KEY)
        if not isinstance(history, list) or not history:
            return {'sessions': 0, 'avg_accuracy': 0.0}
        avg = sum(float(item.get('accuracy', 0.0)) for item in history) / len(history)
        return {'sessions': len(history), 'avg_accuracy': avg}

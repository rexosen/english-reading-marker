"""Listening self-assessment marks kept in the local data directory.

Marks bind to an article sync id plus sentence range and text; a mark whose
stored text no longer matches the article is treated as absent, so edits drop
stale marks without deleting data. Marks are desktop-local training state and
are not part of the phone sync payload.
"""
from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ('heard', 'missed')


class ListeningReviews:
    def __init__(self, path):
        self.path = Path(path)
        self._data = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding='utf-8'))
                if isinstance(loaded, dict):
                    self._data = loaded
            except (ValueError, OSError):
                self._data = {}

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

    def status(self, article_id, start, end, text):
        record = self._data.get(article_id, {}).get(f'{start}:{end}')
        return record['status'] if record and record['text'] == text else None

    def missed(self, article_id, sentences):
        """Sentences of this article marked 'missed' and still matching the text."""
        current = {(start, end): text for start, end, text in sentences}
        result = []
        for record in self._data.get(article_id, {}).values():
            span = (record['start'], record['end'])
            if record['status'] == 'missed' and current.get(span) == record['text']:
                result.append((span[0], span[1], record['text']))
        return sorted(result)

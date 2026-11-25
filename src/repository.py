from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from src.domain import normalize_article_text, sentence_for_range


class ReaderRepository:
    def __init__(self, database_path: Path | str):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def _initialize(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                start INTEGER NOT NULL,
                end INTEGER NOT NULL,
                word TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(article_id, start, end)
            );
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                start INTEGER,
                end INTEGER,
                word TEXT NOT NULL,
                definition TEXT NOT NULL DEFAULT '',
                context TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(article_id, start, end)
            );
            """
        )
        self.connection.commit()
        self._allow_manual_vocabulary()
        from src.lan_sync import initialize_sync
        initialize_sync(self.database_path)

    def _allow_manual_vocabulary(self) -> None:
        """Drop NOT NULL from vocabulary.article_id so user-authored entries can live here.

        A hand-written word or phrase has no article position, so it stores NULL for
        ``article_id``/``start``/``end``; SQLite keeps ``UNIQUE(article_id, start, end)``
        satisfied because NULLs never collide. Rebuilding the table also drops its sync
        triggers, which ``initialize_sync`` re-creates right after this method.
        """
        columns = {row["name"]: dict(row) for row in self.connection.execute("PRAGMA table_info(vocabulary)")}
        if not columns or not columns["article_id"]["notnull"]:
            return
        if self.connection.execute("SELECT COUNT(*) FROM vocabulary").fetchone()[0]:
            from src.storage import backup_database
            backup_database(self.database_path)
        self.connection.executescript(
            """
            PRAGMA foreign_keys = OFF;
            CREATE TABLE vocabulary_manual_ready (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                article_id INTEGER REFERENCES articles(id) ON DELETE CASCADE,
                start INTEGER,
                end INTEGER,
                word TEXT NOT NULL,
                definition TEXT NOT NULL DEFAULT '',
                context TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(article_id, start, end)
            );
            INSERT INTO vocabulary_manual_ready(id, article_id, start, end, word, definition, context, created_at)
                SELECT id, article_id, start, end, word, definition, context, created_at FROM vocabulary;
            DROP TABLE vocabulary;
            ALTER TABLE vocabulary_manual_ready RENAME TO vocabulary;
            PRAGMA foreign_keys = ON;
            """
        )
        self.connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def create_article(self, title: str, text: str) -> int:
        normalized_text = normalize_article_text(text)
        if not title.strip() or not normalized_text:
            raise ValueError("文章标题和正文不能为空")
        cursor = self.connection.execute(
            "INSERT INTO articles(title, text, created_at) VALUES (?, ?, ?)",
            (title.strip(), normalized_text, self._now()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def rename_article(self, article_id: int, title: str) -> None:
        title = title.strip()
        if not title:
            raise ValueError("文章名称不能为空。")
        with self.connection:
            cursor = self.connection.execute(
                "UPDATE articles SET title = ? WHERE id = ?", (title, article_id)
            )
            if cursor.rowcount != 1:
                raise ValueError("文章不存在，请重新选择。")

    def update_article_text(self, article_id: int, text: str) -> tuple[int, int]:
        """Update an article's body text and drop annotations/vocabulary whose span no longer matches."""
        normalized_text = normalize_article_text(text)
        if not normalized_text:
            raise ValueError("文章正文不能为空。")
        article = self.get_article(article_id)
        if article is None:
            raise ValueError("文章不存在，请重新选择。")
        removed_annotations = 0
        removed_vocabulary = 0
        with self.connection:
            self.connection.execute("UPDATE articles SET text = ? WHERE id = ?", (normalized_text, article_id))
            for row in self.connection.execute(
                "SELECT id, start, end, word FROM annotations WHERE article_id = ?", (article_id,)
            ).fetchall():
                if not (0 <= row["start"] < row["end"] <= len(normalized_text)) or normalized_text[row["start"]:row["end"]] != row["word"]:
                    self.connection.execute("DELETE FROM annotations WHERE id = ?", (row["id"],))
                    removed_annotations += 1
            for row in self.connection.execute(
                "SELECT id, start, end, word FROM vocabulary WHERE article_id = ?", (article_id,)
            ).fetchall():
                if not (0 <= row["start"] < row["end"] <= len(normalized_text)) or normalized_text[row["start"]:row["end"]] != row["word"]:
                    self.connection.execute("DELETE FROM vocabulary WHERE id = ?", (row["id"],))
                    removed_vocabulary += 1
            self.connection.execute("INSERT INTO sync_journal(kind) VALUES ('article')")
        return removed_annotations, removed_vocabulary

    def delete_article(self, article_id: int) -> None:
        """Delete an article along with its annotations, article-bound vocabulary and sync metadata."""
        row = self.connection.execute(
            "SELECT sync_id FROM sync_articles WHERE article_id = ?", (article_id,)
        ).fetchone()
        sync_id = row["sync_id"] if row else None
        with self.connection:
            self.connection.execute("DELETE FROM sync_conflicts WHERE article_id = ?", (article_id,))
            self.connection.execute("DELETE FROM reading_progress WHERE article_id = ?", (article_id,))
            self.connection.execute("DELETE FROM sync_articles WHERE article_id = ?", (article_id,))
            if sync_id:
                self.connection.execute(
                    "DELETE FROM study_items WHERE key = ? OR key LIKE ?",
                    (f"meta:{sync_id}", f"review:{sync_id}:%"),
                )
            cursor = self.connection.execute("DELETE FROM articles WHERE id = ?", (article_id,))
            if cursor.rowcount != 1:
                raise ValueError("文章不存在，请重新选择。")
            self.connection.execute("INSERT INTO sync_journal(kind) VALUES ('article')")

    def list_articles(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT id, title, text, created_at FROM articles ORDER BY id DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_article(self, article_id: int) -> dict | None:
        row = self.connection.execute(
            "SELECT id, title, text, created_at FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        return dict(row) if row else None

    def add_annotation(self, article_id: int, start: int, end: int, word: str) -> int:
        article = self.get_article(article_id)
        if article is None or start < 0 or end > len(article["text"]) or start >= end:
            raise ValueError("划线位置超出文章范围")
        if article["text"][start:end] != word:
            raise ValueError("划线文字与文章中的指定位置不匹配")
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO annotations(article_id, start, end, word, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (article_id, start, end, word, self._now()),
        )
        self.connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        row = self.connection.execute(
            "SELECT id FROM annotations WHERE article_id = ? AND start = ? AND end = ?",
            (article_id, start, end),
        ).fetchone()
        return int(row["id"])

    def remove_annotation(self, article_id: int, start: int, end: int) -> None:
        self.connection.execute(
            "DELETE FROM annotations WHERE article_id = ? AND start = ? AND end = ?",
            (article_id, start, end),
        )
        self.connection.commit()

    def list_annotations(self, article_id: int) -> list[dict]:
        rows = self.connection.execute(
            "SELECT id, article_id, start, end, word, created_at FROM annotations "
            "WHERE article_id = ? ORDER BY start",
            (article_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def add_vocabulary(
        self, article_id: int, start: int, end: int, word: str, definition: str
    ) -> int:
        article = self.get_article(article_id)
        if article is None or start < 0 or end > len(article["text"]) or start >= end:
            raise ValueError("词汇位置超出文章范围")
        if article["text"][start:end] != word:
            raise ValueError("词汇与文章中的指定位置不匹配")
        context = sentence_for_range(article["text"], start, end)
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO vocabulary"
            "(article_id, start, end, word, definition, context, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (article_id, start, end, word, definition.strip(), context, self._now()),
        )
        self.connection.commit()
        if cursor.lastrowid:
            return int(cursor.lastrowid)
        row = self.connection.execute(
            "SELECT id FROM vocabulary WHERE article_id = ? AND start = ? AND end = ?",
            (article_id, start, end),
        ).fetchone()
        return int(row["id"])

    def list_vocabulary(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT v.id, v.article_id, v.start, v.end, v.word, v.definition, v.context, "
            "v.created_at, COALESCE(a.title, '') AS article_title, "
            "(v.article_id IS NULL) AS manual FROM vocabulary v "
            "LEFT JOIN articles a ON a.id = v.article_id ORDER BY v.created_at DESC, v.id DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def add_manual_vocabulary(self, word: str, definition: str = "", context: str = "") -> int:
        """Save a word or phrase the user typed themselves, with no article position."""
        word = " ".join(str(word or "").split())
        if not word:
            raise ValueError("词组或单词不能为空")
        if len(word) > 200:
            raise ValueError("词条太长（最多 200 字）")
        duplicate = self.connection.execute(
            "SELECT id FROM vocabulary WHERE article_id IS NULL AND word = ? COLLATE NOCASE", (word,)
        ).fetchone()
        if duplicate:
            raise ValueError(f"“{word}”已经在生词本里了")
        cursor = self.connection.execute(
            "INSERT INTO vocabulary(article_id, start, end, word, definition, context, created_at) "
            "VALUES (NULL, NULL, NULL, ?, ?, ?, ?)",
            (word, str(definition or "").strip(), str(context or "").strip(), self._now()),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def update_vocabulary(self, vocabulary_id: int, *, word: str | None = None,
                          definition: str | None = None, context: str | None = None) -> None:
        """Edit a saved entry. Only hand-written entries may change their wording,
        because an article entry's word must keep matching its underline position."""
        row = self.connection.execute("SELECT article_id FROM vocabulary WHERE id = ?", (vocabulary_id,)).fetchone()
        if row is None:
            raise ValueError("词条不存在，请刷新后重试")
        changes: dict[str, str] = {}
        if word is not None:
            if row["article_id"] is not None:
                raise ValueError("来自文章的词条不能改单词，请删除后重新划词")
            cleaned = " ".join(str(word).split())
            if not cleaned:
                raise ValueError("词组或单词不能为空")
            if len(cleaned) > 200:
                raise ValueError("词条太长（最多 200 字）")
            clash = self.connection.execute(
                "SELECT id FROM vocabulary WHERE article_id IS NULL AND word = ? COLLATE NOCASE AND id != ?",
                (cleaned, vocabulary_id),
            ).fetchone()
            if clash:
                raise ValueError(f"“{cleaned}”已经在生词本里了")
            changes["word"] = cleaned
        if definition is not None:
            changes["definition"] = str(definition).strip()
        if context is not None:
            changes["context"] = str(context).strip()
        if not changes:
            return
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with self.connection:
            self.connection.execute(f"UPDATE vocabulary SET {assignments} WHERE id = ?",
                                    (*changes.values(), vocabulary_id))

    def delete_vocabulary(self, vocabulary_id: int | list[int] | tuple[int, ...]) -> int:
        """Remove word entries; the sync journal bumps so phones drop them too."""
        ids = [vocabulary_id] if isinstance(vocabulary_id, int) else list(vocabulary_id)
        if not ids:
            return 0
        with self.connection:
            self.connection.executemany("DELETE FROM vocabulary WHERE id = ?", [(int(value),) for value in ids])
        return len(ids)

    def sync_revision(self):
        from src.lan_sync import revision
        return revision(self.connection)

    def save_progress(self, article_id, offset):
        with self.connection:
            self.connection.execute(
                "INSERT INTO reading_progress VALUES (?,?) ON CONFLICT(article_id) DO UPDATE SET offset=excluded.offset",
                (article_id, offset),
            )

    def get_progress(self, article_id):
        row = self.connection.execute("SELECT offset FROM reading_progress WHERE article_id=?", (article_id,)).fetchone()
        return row[0] if row else 0

    def close(self) -> None:
        self.connection.close()

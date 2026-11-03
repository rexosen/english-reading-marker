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
                article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                start INTEGER NOT NULL,
                end INTEGER NOT NULL,
                word TEXT NOT NULL,
                definition TEXT NOT NULL DEFAULT '',
                context TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(article_id, start, end)
            );
            """
        )
        self.connection.commit()
        from src.lan_sync import initialize_sync
        initialize_sync(self.database_path)

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
            "v.created_at, a.title AS article_title FROM vocabulary v "
            "JOIN articles a ON a.id = v.article_id ORDER BY v.created_at DESC, v.id DESC"
        ).fetchall()
        return [dict(row) for row in rows]

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

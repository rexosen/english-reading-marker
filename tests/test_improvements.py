from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from PySide6.QtWidgets import QApplication

from src import dictionary
from src.lan_sync import LanSyncService, apply_operation, connect, revision
from src.main import MainWindow
from src.neural_speech import split_chunks
from src.repository import ReaderRepository
from src.storage import audio_cache_stats, clear_audio_cache, prune_daily_backups
from src.study import StudyRepository


class ImprovementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "reader.sqlite3"
        self.repo = ReaderRepository(self.db_path)

    def tearDown(self) -> None:
        self.repo.close()
        self.temp_dir.cleanup()

    def test_delete_article_and_update_article_text(self) -> None:
        article_id = self.repo.create_article("Test Article", "Alpha beta gamma. Delta epsilon.")
        self.repo.add_annotation(article_id, 0, 5, "Alpha")
        self.repo.add_annotation(article_id, 18, 23, "Delta")
        self.repo.add_vocabulary(article_id, 0, 5, "Alpha", "阿尔法")
        self.repo.add_vocabulary(article_id, 18, 23, "Delta", "德尔塔")
        self.repo.save_progress(article_id, 10)
        rev_before = self.repo.sync_revision()

        # Edit text: "Alpha" stays at 0..5, "Delta" shifts/changes -> only Delta is dropped.
        removed_ann, removed_vocab = self.repo.update_article_text(article_id, "Alpha beta gamma. Changed text.")
        self.assertEqual(removed_ann, 1)
        self.assertEqual(removed_vocab, 1)
        self.assertEqual([a["word"] for a in self.repo.list_annotations(article_id)], ["Alpha"])
        self.assertEqual([v["word"] for v in self.repo.list_vocabulary()], ["Alpha"])
        self.assertGreater(self.repo.sync_revision(), rev_before)

        # Delete article cleans up sync_articles, reading_progress, annotations, vocabulary.
        rev_before_delete = self.repo.sync_revision()
        self.repo.delete_article(article_id)
        self.assertIsNone(self.repo.get_article(article_id))
        self.assertEqual(self.repo.list_vocabulary(), [])
        self.assertGreater(self.repo.sync_revision(), rev_before_delete)

    def test_sync_manual_vocabulary_upsert_and_inplace_rename(self) -> None:
        db = connect(self.db_path)
        try:
            apply_operation(db, {"id": "op1", "type": "vocabulary_manual", "word": "in demand", "definition": "紧俏", "context": "A"}, "phone1")
            row1 = db.execute("SELECT id, word, definition, context FROM vocabulary WHERE article_id IS NULL").fetchone()
            self.assertEqual(row1["definition"], "紧俏")

            # Edit definition/context without renaming must update in place.
            apply_operation(db, {"id": "op2", "type": "vocabulary_manual", "word": "in demand", "definition": "非常抢手", "context": "B"}, "phone1")
            row2 = db.execute("SELECT id, word, definition, context FROM vocabulary WHERE article_id IS NULL").fetchone()
            self.assertEqual(row2["id"], row1["id"])
            self.assertEqual(row2["definition"], "非常抢手")
            self.assertEqual(row2["context"], "B")

            # Rename via old_word must preserve id so review:manual:<id> stays linked.
            apply_operation(db, {"id": "op3", "type": "vocabulary_manual", "old_word": "in demand", "word": "in high demand", "definition": "极其抢手", "context": "C"}, "phone1")
            row3 = db.execute("SELECT id, word, definition FROM vocabulary WHERE article_id IS NULL").fetchone()
            self.assertEqual(row3["id"], row1["id"])
            self.assertEqual(row3["word"], "in high demand")
            self.assertEqual(row3["definition"], "极其抢手")
            db.commit()
        finally:
            db.close()

    def test_sync_delete_article_and_unchanged_revision_short_circuit(self) -> None:
        article_id = self.repo.create_article("To Delete", "Hello world.")
        sync_id = StudyRepository(self.repo).sync_id(article_id)
        service = LanSyncService(self.db_path)
        port = service.start(host="127.0.0.1", port=0)
        try:
            code = service.new_pairing_code()
            req = Request(f"http://127.0.0.1:{port}/pair", data=json.dumps({"code": code}).encode(), headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(req, timeout=5) as resp:
                paired = json.loads(resp.read().decode())
            token = paired["token"]

            def post_sync(body: dict) -> dict:
                r = Request(f"http://127.0.0.1:{port}/sync", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}, method="POST")
                with urlopen(r, timeout=5) as resp:
                    return json.loads(resp.read().decode())

            full = post_sync({"client_id": "phone1", "operations": []})
            self.assertFalse(full.get("unchanged", False))
            self.assertEqual(len(full["articles"]), 1)

            # Polling with the same revision and no ops should short-circuit.
            short = post_sync({"client_id": "phone1", "revision": full["revision"], "operations": []})
            self.assertTrue(short.get("unchanged"))
            self.assertNotIn("articles", short)

            # Sending delete op removes the article on desktop.
            after_delete = post_sync({"client_id": "phone1", "operations": [{"id": "del1", "type": "delete", "article_id": sync_id}]})
            self.assertEqual(after_delete["articles"], [])
            self.assertIsNone(self.repo.get_article(article_id))
        finally:
            service.stop()

    def test_google_cooldown_skips_google_after_failure(self) -> None:
        calls: list[str] = []

        class _FakeResponse:
            def __init__(self, payload: dict):
                self._payload = json.dumps(payload).encode("utf-8")
            def read(self):
                return self._payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        def fake_urlopen(req, timeout=4):
            url = req.full_url
            calls.append(url)
            if "googleapis" in url:
                raise OSError("timeout")
            return _FakeResponse({"responseStatus": 200, "responseData": {"translatedText": "你好世界"}})

        dictionary._google_blocked_until = 0.0
        with patch.object(dictionary, "urlopen", side_effect=fake_urlopen):
            self.assertEqual(dictionary._translate_chunk("hello world", 2.0), "你好世界")
            self.assertGreater(dictionary._google_blocked_until, time.monotonic())
            calls.clear()
            self.assertEqual(dictionary._translate_chunk("good morning", 2.0), "你好世界")
            self.assertEqual(len(calls), 1)
            self.assertIn("mymemory", calls[0])
        dictionary._google_blocked_until = 0.0

    def test_neural_split_chunks(self) -> None:
        text = " ".join([f"Sentence number {i} is here for testing chunk splitting." for i in range(15)])
        chunks = split_chunks(text, limit=160)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(c) <= 160 for c in chunks))
        self.assertEqual(" ".join(chunks), text)

    def test_storage_prune_and_audio_cache(self) -> None:
        backups = self.root / "backups"
        backups.mkdir()
        for day in range(1, 36):
            (backups / f"daily_202601{day:02d}.sqlite3").write_bytes(b"x")
        (backups / "manual_20260101_000000_000000.sqlite3").write_bytes(b"keep")
        removed = prune_daily_backups(backups, keep=30)
        self.assertEqual(removed, 5)
        self.assertEqual(len(list(backups.glob("daily_*.sqlite3"))), 30)
        self.assertTrue((backups / "manual_20260101_000000_000000.sqlite3").exists())

        (self.root / "neural").mkdir()
        (self.root / "pronunciation").mkdir()
        (self.root / "neural" / "a.mp3").write_bytes(b"12345")
        (self.root / "pronunciation" / "b.mp3").write_bytes(b"123")
        self.assertEqual(audio_cache_stats(self.root), (2, 8))
        self.assertEqual(clear_audio_cache(self.root), 2)
        self.assertEqual(audio_cache_stats(self.root), (0, 0))

    def test_vocabulary_search_and_dictation_dedup(self) -> None:
        self.repo.add_manual_vocabulary("in demand", "非常抢手", "Engineers are in demand.")
        self.repo.add_manual_vocabulary("take over", "接管", "She will take over the team.")
        window = MainWindow(self.repo, self.root / "missing.txt", seed_sample=False)
        try:
            window.vocabulary_search.setText("抢手")
            self.assertEqual(window.vocabulary_list.count(), 1)
            self.assertIn("in demand", window.vocabulary_list.item(0).text())
            window.vocabulary_search.clear()
            self.assertEqual(window.vocabulary_list.count(), 2)

            # Dictation check on the same sentence twice should not inflate sentence count.
            sentences = [(0, 11, "Hello world")]
            state = {"index": 0, "results": {}}
            from PySide6.QtWidgets import QLabel, QTextBrowser, QTextEdit
            typed, feedback, info = QTextEdit(), QTextBrowser(), QLabel()
            typed.setPlainText("hello")
            window._dictation_check(sentences, state, typed, feedback, info)
            self.assertIn("已对照 1 句", info.text())
            typed.setPlainText("hello world")
            window._dictation_check(sentences, state, typed, feedback, info)
            self.assertIn("已对照 1 句", info.text())
            self.assertIn("100%", info.text())
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()

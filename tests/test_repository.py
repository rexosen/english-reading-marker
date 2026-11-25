import tempfile
import unittest
from pathlib import Path

from src.repository import ReaderRepository


class ReaderRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = ReaderRepository(Path(self.temp_dir.name) / "reader.sqlite3")
        self.article_id = self.repository.create_article(
            "Online Classes", "Students learn. Other students work."
        )

    def tearDown(self):
        self.repository.close()
        self.temp_dir.cleanup()

    def test_annotation_is_attached_to_one_exact_occurrence(self):
        article = self.repository.get_article(self.article_id)
        first_start = article["text"].index("Students")
        second_start = article["text"].index("students")

        self.repository.add_annotation(
            self.article_id, second_start, second_start + len("students"), "students"
        )

        annotations = self.repository.list_annotations(self.article_id)
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["start"], second_start)
        self.assertNotEqual(annotations[0]["start"], first_start)

    def test_annotation_rejects_offsets_that_do_not_match_the_word(self):
        with self.assertRaises(ValueError):
            self.repository.add_annotation(self.article_id, 0, 8, "students")

    def test_duplicate_annotation_reuses_existing_record(self):
        start = 0
        first_id = self.repository.add_annotation(self.article_id, start, len("Students"), "Students")
        second_id = self.repository.add_annotation(self.article_id, start, len("Students"), "Students")

        self.assertEqual(first_id, second_id)
        self.assertEqual(len(self.repository.list_annotations(self.article_id)), 1)

    def test_missing_article_returns_none(self):
        self.assertIsNone(self.repository.get_article(9999))

    def test_vocabulary_is_saved_independently_of_underlines(self):
        article = self.repository.get_article(self.article_id)
        word_start = article["text"].index("students")

        self.repository.add_vocabulary(
            self.article_id,
            word_start,
            word_start + len("students"),
            "students",
            "学生（复数）",
        )

        self.assertEqual(self.repository.list_annotations(self.article_id), [])
        vocabulary = self.repository.list_vocabulary()
        self.assertEqual(len(vocabulary), 1)
        self.assertEqual(vocabulary[0]["word"], "students")
        self.assertEqual(vocabulary[0]["definition"], "学生（复数）")
        self.assertEqual(vocabulary[0]["context"], "Other students work.")

    def test_rename_updates_title_and_preserves_linked_data(self):
        self.repository.add_annotation(self.article_id, 0, 8, "Students")
        self.repository.add_vocabulary(self.article_id, 0, 8, "Students", "学生")
        before = self.repository.get_article(self.article_id)
        self.repository.rename_article(self.article_id, " New title ")
        after = self.repository.get_article(self.article_id)
        self.assertEqual(after["title"], "New title")
        self.assertEqual(after["text"], before["text"])
        self.assertEqual(after["created_at"], before["created_at"])
        self.assertEqual(len(self.repository.list_annotations(self.article_id)), 1)
        self.assertEqual(self.repository.list_vocabulary()[0]["article_title"], "New title")

    def test_rename_rejects_empty_title_and_missing_article(self):
        with self.assertRaises(ValueError):
            self.repository.rename_article(self.article_id, "  ")
        with self.assertRaises(ValueError):
            self.repository.rename_article(99999, "New name")


    def test_manual_entries_have_no_article_position(self):
        vocabulary_id = self.repository.add_manual_vocabulary("  in   demand ", "有需求的", "Jobs are in demand.")
        record = [entry for entry in self.repository.list_vocabulary() if entry["id"] == vocabulary_id][0]
        self.assertEqual(record["word"], "in demand")
        self.assertIsNone(record["article_id"])
        self.assertIsNone(record["start"])
        self.assertEqual(record["context"], "Jobs are in demand.")
        self.assertEqual(record["article_title"], "")
        self.assertEqual(record["manual"], 1)
        # article-bound entries keep their binding and title
        article_entry = [entry for entry in self.repository.list_vocabulary() if not entry["manual"]]
        self.assertEqual(article_entry, [])

    def test_manual_entries_reject_empty_and_duplicate_wording(self):
        self.repository.add_manual_vocabulary("take over", "接管")
        with self.assertRaises(ValueError):
            self.repository.add_manual_vocabulary("   ")
        with self.assertRaises(ValueError):
            self.repository.add_manual_vocabulary("TAKE  OVER", "重复")
        self.assertEqual(len([entry for entry in self.repository.list_vocabulary() if entry["manual"]]), 1)

    def test_manual_entries_can_be_edited_and_article_wording_stays_locked(self):
        vocabulary_id = self.repository.add_manual_vocabulary("put off", "推迟")
        self.repository.update_vocabulary(vocabulary_id, word="put  off", definition="推迟；拖延", context="The match was put off.")
        record = self.repository.list_vocabulary()[0]
        self.assertEqual((record["word"], record["definition"]), ("put off", "推迟；拖延"))
        article = self.repository.get_article(self.article_id)
        start = article["text"].index("Students")
        article_entry = self.repository.add_vocabulary(self.article_id, start, start + 8, "Students", "学生")
        with self.assertRaises(ValueError):
            self.repository.update_vocabulary(article_entry, word="Learners")
        self.repository.update_vocabulary(article_entry, definition="学生们")
        edited = [entry for entry in self.repository.list_vocabulary() if entry["id"] == article_entry][0]
        self.assertEqual(edited["definition"], "学生们")
        self.assertEqual(edited["word"], "Students")
        with self.assertRaises(ValueError):
            self.repository.update_vocabulary(article_entry, word="x")

    def test_old_schema_is_migrated_without_losing_words(self):
        import sqlite3

        path = Path(self.temp_dir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(path)
        connection.executescript(
            """
            CREATE TABLE articles (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE annotations (id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                start INTEGER NOT NULL, end INTEGER NOT NULL, word TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(article_id, start, end));
            CREATE TABLE vocabulary (id INTEGER PRIMARY KEY AUTOINCREMENT, article_id INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                start INTEGER NOT NULL, end INTEGER NOT NULL, word TEXT NOT NULL, definition TEXT NOT NULL DEFAULT '',
                context TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, UNIQUE(article_id, start, end));
            INSERT INTO articles(title, text, created_at) VALUES('阅读:老库', 'Online classes are compatible.', datetime('now'));
            INSERT INTO vocabulary(article_id, start, end, word, definition, context, created_at)
                VALUES(1, 20, 31, 'compatible', '能共处的', 'Online classes are compatible.', datetime('now'));
            INSERT INTO annotations(article_id, start, end, word, created_at) VALUES(1, 20, 31, 'compatible', datetime('now'));
            """
        )
        connection.commit()
        connection.close()

        migrated = ReaderRepository(path)
        try:
            columns = {row["name"]: dict(row) for row in migrated.connection.execute("PRAGMA table_info(vocabulary)")}
            self.assertFalse(columns["article_id"]["notnull"])
            self.assertFalse(columns["start"]["notnull"])
            rows = migrated.list_vocabulary()
            self.assertEqual([(row["word"], row["start"], row["end"], row["manual"]) for row in rows],
                             [("compatible", 20, 31, 0)])
            self.assertEqual(len(migrated.list_annotations(1)), 1)
            # manual entries and article entries can coexist: NULL positions never collide
            # with the UNIQUE(article_id, start, end) index
            first = migrated.add_manual_vocabulary("in demand", "有需求的")
            second = migrated.add_manual_vocabulary("take over", "接管")
            self.assertNotEqual(first, second)
            self.assertEqual(len(migrated.list_vocabulary()), 3)
            self.assertEqual([row[0] for row in migrated.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'sync_word%' ORDER BY name")],
                ["sync_word_add", "sync_word_change", "sync_word_remove"])
            self.assertEqual(migrated.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            migrated.close()


if __name__ == "__main__":
    unittest.main()

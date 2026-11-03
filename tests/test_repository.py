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


if __name__ == "__main__":
    unittest.main()

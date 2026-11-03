import json
import tempfile
import unittest
from pathlib import Path

from src.listening import ListeningReviews


class ListeningReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "listening_reviews.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_mark_persists_and_reloads(self):
        store = ListeningReviews(self.path)
        store.mark("a1", 0, 12, "Hello there.", "missed")
        reloaded = ListeningReviews(self.path)
        self.assertEqual(reloaded.status("a1", 0, 12, "Hello there."), "missed")
        self.assertEqual(reloaded.missed("a1", [(0, 12, "Hello there.")]), [(0, 12, "Hello there.")])

    def test_stale_text_after_article_edit_is_dropped(self):
        store = ListeningReviews(self.path)
        store.mark("a1", 0, 12, "Hello there.", "missed")
        self.assertIsNone(store.status("a1", 0, 12, "Hello here!"))
        self.assertEqual(store.missed("a1", [(0, 12, "Hello here!")]), [])

    def test_heard_replaces_missed_and_none_clears(self):
        store = ListeningReviews(self.path)
        store.mark("a1", 0, 12, "Hello there.", "missed")
        store.mark("a1", 0, 12, "Hello there.", "heard")
        self.assertEqual(store.status("a1", 0, 12, "Hello there."), "heard")
        self.assertEqual(store.missed("a1", [(0, 12, "Hello there.")]), [])
        store.mark("a1", 0, 12, "Hello there.", None)
        self.assertIsNone(store.status("a1", 0, 12, "Hello there."))

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValueError):
            ListeningReviews(self.path).mark("a1", 0, 1, "a", "maybe")

    def test_corrupt_file_restarts_empty_store(self):
        self.path.write_text("{not json", encoding="utf-8")
        store = ListeningReviews(self.path)
        store.mark("a1", 0, 1, "a", "heard")
        self.assertEqual(store.status("a1", 0, 1, "a"), "heard")

    def test_saved_file_is_valid_json(self):
        store = ListeningReviews(self.path)
        store.mark("a1", 0, 12, "Hello there.", "heard")
        json.loads(self.path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

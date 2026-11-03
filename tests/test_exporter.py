import csv
import tempfile
import unittest
from pathlib import Path

from src.exporter import export_vocabulary_csv


class VocabularyExportTests(unittest.TestCase):
    def test_export_writes_excel_friendly_csv_with_article_and_context(self):
        records = [
            {
                "word": "infrequent",
                "definition": "不频繁的",
                "context": "Live sessions are infrequent.",
                "article_title": "Online Classes",
                "created_at": "2026-10-23T12:00:00",
            }
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "vocabulary.csv"
            export_vocabulary_csv(records, output_path)

            raw = output_path.read_bytes()
            self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
            with output_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                exported = list(csv.DictReader(csv_file))

        self.assertEqual(exported[0]["单词"], "infrequent")
        self.assertEqual(exported[0]["中文释义"], "不频繁的")
        self.assertEqual(exported[0]["原句"], "Live sessions are infrequent.")
        self.assertEqual(exported[0]["文章"], "Online Classes")


if __name__ == "__main__":
    unittest.main()

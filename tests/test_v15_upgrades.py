import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.dictionary import format_translation_html, lemmatize_candidates, lookup_local_entry
from src.importers import import_article_file, make_qr_matrix, render_qr_pixmap
from src.main import MainWindow
from src.repository import ReaderRepository
from src.theme import build_stylesheet, is_dark_theme


class V15UpgradesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.sample_path = Path(__file__).resolve().parent.parent / "assets" / "Online_Classes_原文.txt"
        self.repository = ReaderRepository(self.root / "reader.sqlite3")
        self.window = MainWindow(self.repository, self.sample_path)
        self.window.audio_engine = "system"
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.repository.close()
        self.temp_dir.cleanup()

    def test_global_dark_theme_updates_window_and_delegates(self):
        self.assertFalse(is_dark_theme("paper"))
        self.assertTrue(is_dark_theme("dark"))
        self.window.display_options["theme"] = "dark"
        self.window.apply_display()
        self.assertIn("#121720", self.window.styleSheet())
        self.assertEqual(self.window.article_delegate.theme_name, "dark")
        self.assertEqual(self.window.vocab_delegate.theme_name, "dark")
        self.assertIn("#1b222e", self.window.reader._background_options["background"])
        self.assertIn("#232c3b", build_stylesheet("dark"))

    def test_lemmatization_and_rich_html_formatting(self):
        self.assertIn("study", lemmatize_candidates("studied"))
        self.assertIn("run", lemmatize_candidates("running"))
        self.assertIn("good", lemmatize_candidates("better"))
        self.assertIn("mouse", lemmatize_candidates("mice"))
        entry = lookup_local_entry("studied")
        self.assertIsNotNone(entry)
        rendered = format_translation_html(
            "study",
            "n. 学习；研究\nv. 学习",
            entry={"phonetic": "ˈstʌdi", "tag": "cet4 ielts", "collins": "4"},
            dark=True,
        )
        self.assertIn("/ˈstʌdi/", rendered)
        self.assertIn("四级", rendered)
        self.assertIn("雅思", rendered)
        self.assertIn("★★★★", rendered)

    def test_importers_support_markdown_and_epub(self):
        md_path = self.root / "notes.md"
        md_path.write_text("# Heading\n\nSome **bold** and [link](https://example.com) text.", encoding="utf-8")
        title, text = import_article_file(md_path)
        self.assertEqual(title, "notes")
        self.assertEqual(text, "Heading\n\nSome bold and link text.")

        epub_path = self.root / "sample.epub"
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("chapter1.xhtml", "<html><body><h1>Chapter 1</h1><p>Hello EPUB world.</p></body></html>")
        title, text = import_article_file(epub_path)
        self.assertEqual(title, "sample")
        self.assertIn("Chapter 1", text)
        self.assertIn("Hello EPUB world.", text)

    def test_pure_python_qr_code_generation(self):
        matrix = make_qr_matrix("http://192.168.1.10:8765?code=123456")
        self.assertGreaterEqual(len(matrix), 21)
        self.assertEqual(len(matrix), len(matrix[0]))
        pix = render_qr_pixmap("http://192.168.1.10:8765?code=123456", 160)
        self.assertFalse(pix.isNull())
        self.assertEqual(pix.width(), 160)

    def test_one_click_save_vocabulary_auto_looks_up_cached_word(self):
        article = self.repository.list_articles()[0]
        word = "students"
        start = article["text"].index(word)
        cursor = self.window.reader.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(start + len(word), QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)
        with patch("src.main.cached_translation", return_value="n. 学生"):
            self.window.save_vocabulary()
        saved = self.repository.list_vocabulary()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["word"], word)
        self.assertEqual(saved[0]["definition"], "n. 学生")

    def test_listening_shortcuts_sync_to_study_and_highlight_missed(self):
        QTest.keyClick(self.window.reader, Qt.Key.Key_N)
        sync_id = self.window._current_sync_id()
        self.assertIn(f"listen:{sync_id}", self.window.study.items())
        self.assertGreaterEqual(len(self.window.reader.extraSelections()), 1)

    def test_review_cards_filter_by_category_and_stats(self):
        from src.vocabulary import AUTO_LISTENING, AUTO_READING

        a1 = self.repository.create_article("听力:测试一", "Climate change matters.")
        a2 = self.repository.create_article("阅读:测试二", "Modern economics evolves.")
        self.repository.add_vocabulary(a1, 0, 7, "Climate", "气候")
        self.repository.add_vocabulary(a2, 0, 6, "Modern", "现代的")
        info = self.window._vocabulary_article_info()
        listening_cards = self.window.study.review_cards(all_cards=True, category=AUTO_LISTENING, article_info=info)
        reading_cards = self.window.study.review_cards(all_cards=True, category=AUTO_READING, article_info=info)
        self.assertEqual([c["word"] for c in listening_cards], ["Climate"])
        self.assertEqual([c["word"] for c in reading_cards], ["Modern"])

        stats = self.window.study.stats(article_info=info, listening=self.window.listening)
        self.assertEqual(stats["total_vocab"], 2)
        self.assertEqual(stats["total_articles"], 3)


if __name__ == "__main__":
    unittest.main()

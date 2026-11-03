import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox

from src.dictionary import DictionaryError
from src.main import ArticleEditorDialog, MainWindow, _resource_path
from src.repository import ReaderRepository


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.sample_path = Path(__file__).resolve().parent.parent / "assets" / "Online_Classes_原文.txt"
        self.repository = ReaderRepository(self.root / "reader.sqlite3")
        self.window = MainWindow(self.repository, self.sample_path)
        self.window.show()
        self.application.processEvents()

    def tearDown(self):
        self.window.close()
        self.repository.close()
        self.temp_dir.cleanup()

    def test_underline_marks_only_the_selected_occurrence(self):
        article = self.repository.list_articles()[0]
        first_start = article["text"].index("students")
        second_start = article["text"].index("students", first_start + 1)
        cursor = self.window.reader.textCursor()
        cursor.setPosition(second_start)
        cursor.setPosition(second_start + len("students"), QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)

        self.window.toggle_underline()

        annotations = self.repository.list_annotations(article["id"])
        self.assertEqual(len(annotations), 1)
        self.assertEqual(annotations[0]["start"], second_start)
        self.assertEqual(annotations[0]["word"], "students")

        reopened_window = MainWindow(self.repository, self.sample_path)
        reopened_window.show()
        self.application.processEvents()
        marked_cursor = reopened_window.reader.textCursor()
        marked_cursor.setPosition(second_start)
        marked_cursor.setPosition(second_start + 1, QTextCursor.MoveMode.KeepAnchor)
        self.assertTrue(marked_cursor.charFormat().fontUnderline())
        reopened_window.close()

    def test_exact_user_article_is_preloaded(self):
        articles = self.repository.list_articles()

        self.assertEqual(articles[0]["title"], "Online Classes")
        self.assertIn("Online classes began to be popularized", articles[0]["text"])
        self.assertIn("restructured online classes", articles[0]["text"])

    def test_reader_lookup_adds_selected_word_to_vocabulary(self):
        article = self.repository.list_articles()[0]
        word_start = article["text"].index("infrequent")
        cursor = self.window.reader.textCursor()
        cursor.setPosition(word_start)
        cursor.setPosition(word_start + len("infrequent"), QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)

        with patch("src.main.cached_translation", return_value=None), patch("src.main.lookup_chinese", return_value="不频繁的"):
            self.window.lookup_selection()
            deadline = time.monotonic() + 3
            while self.window.current_definition != "不频繁的" and time.monotonic() < deadline:
                self.application.processEvents()
                time.sleep(0.01)

        self.assertEqual(self.window.definition_label.text(), "不频繁的")
        self.window.save_vocabulary()
        vocabulary = self.repository.list_vocabulary()
        self.assertEqual(len(vocabulary), 1)
        self.assertEqual(vocabulary[0]["word"], "infrequent")
        self.assertEqual(vocabulary[0]["definition"], "不频繁的")

    def test_lookup_failure_is_shown_in_the_reader(self):
        article = self.repository.list_articles()[0]
        word_start = article["text"].index("infrequent")
        cursor = self.window.reader.textCursor()
        cursor.setPosition(word_start)
        cursor.setPosition(word_start + len("infrequent"), QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)

        with patch("src.main.cached_translation", return_value=None), patch("src.main.lookup_chinese", side_effect=DictionaryError("offline")):
            self.window.lookup_selection()
            deadline = time.monotonic() + 3
            while self.window.definition_label.text().startswith("正在翻译") and time.monotonic() < deadline:
                self.application.processEvents()
                time.sleep(0.01)

        self.assertEqual(self.window.definition_label.text(), "offline")
        self.assertEqual(self.repository.list_vocabulary(), [])

    def test_second_toggle_removes_the_exact_underline(self):
        article = self.repository.list_articles()[0]
        word_start = article["text"].index("infrequent")
        cursor = self.window.reader.textCursor()
        cursor.setPosition(word_start)
        cursor.setPosition(word_start + len("infrequent"), QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)

        self.window.toggle_underline()
        self.window.toggle_underline()

        self.assertEqual(self.repository.list_annotations(article["id"]), [])

    def test_missing_selection_produces_a_hint(self):
        self.window.reader.moveCursor(QTextCursor.MoveOperation.Start)

        self.window.lookup_selection()

        self.assertIn("选中英文内容", self.window.status_label.text())

    def test_text_file_import_saves_after_review_dialog(self):
        source = self.root / "converted_article.txt"
        source.write_text("A reliable connection.\n\nStudents learn.", encoding="utf-8")

        with patch("src.main.QFileDialog.getOpenFileName", return_value=(str(source), "")):
            with patch.object(ArticleEditorDialog, "exec", return_value=QDialog.DialogCode.Accepted):
                self.window.add_text_file()

        articles = self.repository.list_articles()
        imported = next(article for article in articles if article["title"] == "converted_article")
        self.assertEqual(imported["text"], "A reliable connection.\n\nStudents learn.")

    def test_paste_flow_saves_article(self):
        with patch.object(ArticleEditorDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            with patch.object(ArticleEditorDialog, "article", return_value=("Pasted", "A pasted article.")):
                self.window.add_pasted_article()

        self.assertEqual(self.repository.get_article(self.window.current_article_id)["title"], "Pasted")

    def test_export_action_writes_vocabulary_csv(self):
        article = self.repository.get_article(self.window.current_article_id)
        word_start = article["text"].index("infrequent")
        self.repository.add_vocabulary(
            article["id"], word_start, word_start + len("infrequent"), "infrequent", "不频繁的"
        )
        destination = self.root / "exported.csv"

        with patch("src.main.QFileDialog.getSaveFileName", return_value=(str(destination), "")):
            with patch.object(QMessageBox, "information"):
                self.window.export_vocabulary()

        self.assertTrue(destination.exists())
        self.assertIn("infrequent", destination.read_text(encoding="utf-8-sig"))

    def test_export_action_handles_empty_vocabulary(self):
        self.window.export_vocabulary()

        self.assertEqual(self.window.status_label.text(), "生词表还是空的。")

    def test_article_editor_imports_and_normalizes_text(self):
        source = self.root / "draft.txt"
        source.write_bytes(b"First line.\r\n\r\nSecond line.")
        dialog = ArticleEditorDialog(parent=self.window)

        with patch("src.main.QFileDialog.getOpenFileName", return_value=(str(source), "")):
            dialog.import_text()

        self.assertEqual(dialog.title_input.text(), "draft")
        self.assertEqual(dialog.article(), ("draft", "First line.\n\nSecond line."))
        dialog.close()

    def test_resource_path_resolves_bundled_sample(self):
        self.assertEqual(_resource_path("assets/Online_Classes_原文.txt").name, "Online_Classes_原文.txt")

    def test_sample_article_is_loaded_on_first_launch(self):
        articles = self.repository.list_articles()

        self.assertEqual(len(articles), 1)
        self.assertIn("Online classes began to be popularized", articles[0]["text"])
        self.assertEqual(self.window.current_article_id, articles[0]["id"])

    def test_right_click_word_shows_local_definition_without_network(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        cursor = self.window.reader.textCursor()
        cursor.setPosition(3)
        point = self.window.reader.cursorRect(cursor).center()
        with patch("src.main.lookup_chinese") as network:
            QTest.mouseClick(self.window.reader.viewport(), Qt.MouseButton.RightButton, pos=point)
            self.application.processEvents()
            self.assertTrue(self.window.translation_popup.isVisible())
            self.assertIn("联机", self.window.popup_definition.toPlainText())
            network.assert_not_called()

    def test_paragraph_selection_is_preserved_by_right_click(self):
        from PySide6.QtCore import QPoint
        text = self.window.reader.toPlainText()
        end = text.index("\n")
        cursor = self.window.reader.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)
        with patch("src.main.cached_translation", return_value="整段中文译文"):
            self.window.show_translation_popup(QPoint(100, 100))
        self.assertEqual(self.window.current_selection[2], text[:end])
        self.assertEqual(self.window.popup_definition.toPlainText(), "整段中文译文")

    def test_selected_and_article_speech_receive_correct_text(self):
        cursor = self.window.reader.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)
        with patch.object(self.window.speech, "say") as say, patch.object(self.window, "_play_word_audio") as word_audio:
            self.window.speak_selection()
            word_audio.assert_called_with("Online")
            self.window.speak_article()
            say.assert_called_with(self.window.reader.toPlainText())

    def test_late_lookup_result_is_ignored_after_article_change(self):
        previous_id = self.window.lookup_request_id
        article_id = self.repository.create_article("Second", "Different text.")
        self.window.refresh_articles(article_id)
        self.window._on_lookup_finished(previous_id, (0, 6, "Online"), "旧结果")
        self.assertNotEqual(self.window.current_definition, "旧结果")

    def test_long_translation_does_not_expand_window_or_pin_splitter(self):
        from PySide6.QtWidgets import QSplitter
        splitter = self.window.findChild(QSplitter)
        original_width = self.window.width()
        selection = (0, 500, "A very long sentence without line breaks. " * 20)
        self.window._on_lookup_finished(self.window.lookup_request_id, selection, "长段落译文。" * 200)
        self.application.processEvents()
        self.assertEqual(self.window.width(), original_width)
        self.assertLessEqual(splitter.widget(2).width(), 360)
        splitter.setSizes([240, 700, 300])
        self.application.processEvents()
        self.assertGreaterEqual(splitter.widget(0).width(), 180)
        self.assertGreaterEqual(splitter.widget(1).width(), 520)
        self.assertLessEqual(self.window.minimumSizeHint().width(), 1080)

    def test_vocabulary_opens_in_separate_modeless_window(self):
        self.assertFalse(self.window.vocabulary_dialog.isVisible())
        self.window.open_vocabulary()
        self.application.processEvents()
        self.assertTrue(self.window.vocabulary_dialog.isVisible())
        self.assertFalse(self.window.vocabulary_dialog.isModal())
        self.assertFalse(self.window.centralWidget().isAncestorOf(self.window.vocabulary_list))
        self.window.vocabulary_dialog.close()
        self.assertTrue(self.window.isVisible())

    def test_rename_article_preserves_reading_position_and_annotations(self):
        item = self.window.article_list.currentItem()
        article_id = self.window.current_article_id
        cursor = self.window.reader.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)
        self.window.toggle_underline()
        with patch("src.main.QInputDialog.getText", return_value=("  阅读材料一  ", True)):
            self.window.rename_article(item)
        self.assertEqual(self.window.article_list.currentItem().text(), "阅读材料一")
        self.assertEqual(self.window.article_title_label.text(), "阅读材料一")
        self.assertEqual(self.repository.get_article(article_id)["title"], "阅读材料一")
        self.assertEqual(self.window.reader.textCursor().selectedText(), "Online")
        self.assertEqual(len(self.repository.list_annotations(article_id)), 1)

    def test_rename_cancel_or_empty_keeps_original_name(self):
        item = self.window.article_list.currentItem()
        original = item.text()
        for value in [("ignored", False), ("   ", True)]:
            with patch("src.main.QInputDialog.getText", return_value=value):
                self.window.rename_article(item)
            self.assertEqual(item.text(), original)
            self.assertEqual(self.repository.get_article(self.window.current_article_id)["title"], original)

    def test_renaming_other_article_keeps_current_article(self):
        active_id = self.window.current_article_id
        second_id = self.repository.create_article("Another article", "Another body.")
        self.window.refresh_articles(active_id)
        item = next(self.window.article_list.item(i) for i in range(self.window.article_list.count()) if self.window.article_list.item(i).text() == "Another article")
        with patch("src.main.QInputDialog.getText", return_value=("New title", True)):
            self.window.rename_article(item)
        self.assertEqual(self.window.current_article_id, active_id)
        self.assertEqual(self.repository.get_article(second_id)["title"], "New title")

    def test_remote_changes_refresh_without_resetting_reader_selection(self):
        cursor = self.window.reader.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(6, QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)
        article_id = self.window.current_article_id
        self.repository.rename_article(article_id, "Phone title")
        self.repository.add_annotation(article_id, 0, 6, "Online")
        self.window.refresh_from_sync()
        self.assertEqual(self.window.article_title_label.text(), "Phone title")
        self.assertEqual(self.window.reader.textCursor().selectedText(), "Online")
        self.assertTrue(self.window.reader.textCursor().charFormat().fontUnderline())

    def test_word_audio_uses_selected_speed_and_ignores_cancelled_request(self):
        from unittest.mock import MagicMock
        player = MagicMock()
        self.window.word_player = player
        self.window.audio_speed = 0.75
        self.window._on_word_audio(self.window.audio_request_id, "online", self.root / "word.mp3")
        player.setPlaybackRate.assert_called_with(0.75)
        player.play.assert_called_once()
        self.window.stop_audio()
        player.reset_mock()
        self.window._on_word_audio(self.window.audio_request_id - 1, "online", self.root / "word.mp3")
        player.play.assert_not_called()

    def test_audio_settings_save_accent_speed_and_source(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QComboBox
        def change_settings():
            dialog = QApplication.activeModalWidget()
            combos = dialog.findChildren(QComboBox)
            combos[0].setCurrentIndex(combos[0].findData("system"))
            combos[1].setCurrentIndex(combos[1].findData("uk"))
            combos[2].setCurrentIndex(combos[2].findData(0.6))
            dialog.accept()
        QTimer.singleShot(0, change_settings)
        self.window.open_audio_settings()
        self.assertEqual(self.window.audio_accent, "uk")
        self.assertEqual(self.window.audio_speed, 0.6)
        self.assertEqual(self.window.audio_source, "system")
        self.assertEqual(self.window.audio_settings.value("accent"), "uk")

    def test_audio_settings_offer_above_exam_speed(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QComboBox
        def change_settings():
            dialog = QApplication.activeModalWidget()
            combos = dialog.findChildren(QComboBox)
            combos[2].setCurrentIndex(combos[2].findData(1.25))
            dialog.accept()
        QTimer.singleShot(0, change_settings)
        self.window.open_audio_settings()
        self.assertEqual(self.window.audio_speed, 1.25)
        self.assertEqual(float(self.window.audio_settings.value("speed")), 1.25)

    def test_listening_marks_drive_replay_order(self):
        from src.study import sentence_ranges
        self.window._sentences = sentence_ranges(self.window.reader.toPlainText())
        self.assertGreaterEqual(len(self.window._sentences), 4)
        self.window._sentence_index = 1
        self.window._mark_sentence("missed")
        self.window._sentence_index = 3
        self.window._mark_sentence("missed")
        sync_id = self.window._current_sync_id()
        self.assertEqual(len(self.window.listening.missed(sync_id, self.window._sentences)), 2)
        self.window.replay_missed.setChecked(True)
        self.assertEqual(self.window._sentence_order(), [1, 3])
        self.window._sentence_index = 1
        self.window.step_sentence(1)
        self.assertEqual(self.window._sentence_index, 3)
        self.window.step_sentence(1)
        self.assertEqual(self.window._sentence_index, 3)
        self.window.cancel_sentence_sequence()


if __name__ == "__main__":
    unittest.main()

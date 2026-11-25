import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
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
        self.window.audio_engine = "system"  # keep tests offline: neural engine is covered by dedicated tests
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

    def test_neural_engine_routes_sentence_and_article_reading(self):
        self.window.audio_engine = "neural"
        with patch.object(self.window.neural, "say") as neural_say, patch.object(self.window.speech, "say") as sapi_say:
            self.window.speak_article()
            neural_say.assert_called_once()
            text, accent, speed = neural_say.call_args[0]
            self.assertEqual(text, self.window.reader.toPlainText())
            self.assertEqual(accent, self.window.audio_accent)
            self.assertEqual(speed, self.window.audio_speed)
            sapi_say.assert_not_called()
        with patch.object(self.window.speech, "say") as sapi_say, patch.object(self.window.speech, "availableVoices", return_value=["voice"]):
            self.window._on_neural_failed("Some sentence.", "断网了。")
            sapi_say.assert_called_once_with("Some sentence.")

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
            combos[3].setCurrentIndex(combos[3].findData("neural"))
            dialog.accept()
        QTimer.singleShot(0, change_settings)
        self.window.open_audio_settings()
        self.assertEqual(self.window.audio_accent, "uk")
        self.assertEqual(self.window.audio_speed, 0.6)
        self.assertEqual(self.window.audio_source, "system")
        self.assertEqual(self.window.audio_engine, "neural")
        self.assertEqual(self.window.audio_settings.value("accent"), "uk")
        self.assertEqual(self.window.audio_settings.value("engine"), "neural")

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

    def test_space_and_plain_arrows_emit_reader_shortcut_signals(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        toggles, steps = [], []
        self.window.reader.speech_toggle_requested.connect(lambda: toggles.append(1))
        self.window.reader.sentence_step_requested.connect(steps.append)
        with patch.object(self.window, "_speak_system"):
            QTest.keyClick(self.window.reader, Qt.Key.Key_Space)
            QTest.keyClick(self.window.reader, Qt.Key.Key_Down)
            QTest.keyClick(self.window.reader, Qt.Key.Key_Up)
        self.assertEqual(toggles, [1])
        self.assertEqual(steps, [1, -1])
        with patch.object(self.window, "_speak_system"):
            QTest.keyClick(self.window.reader, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
            QTest.keyClick(self.window.reader, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual((toggles, steps), ([1], [1, -1]))
        self.window.cancel_sentence_sequence()

    def test_keyboard_sentence_step_starts_from_cursor_then_steps(self):
        self.window.cancel_sentence_sequence()
        with patch.object(self.window, "_speak_system"), patch.object(self.window, "start_sentences") as start:
            self.window.keyboard_sentence_step(1)
            start.assert_called_once()
        with patch.object(self.window, "_speak_system"), patch.object(self.window, "start_sentences"), \
                patch.object(self.window, "step_sentence") as step:
            self.window._sentence_active = True
            self.window.keyboard_sentence_step(-1)
            step.assert_called_once_with(-1)
        self.window.cancel_sentence_sequence()

    def sentence_viewport_band(self, start, end):
        """Viewport-relative rectangles of the first and last line of a sentence."""
        from src.domain import python_offset_to_qt

        text = self.window.reader.toPlainText()
        document = self.window.reader.document()
        head = QTextCursor(document)
        head.setPosition(python_offset_to_qt(text, start))
        tail = QTextCursor(document)
        tail.setPosition(python_offset_to_qt(text, max(start, end - 1)))
        return self.window.reader.cursorRect(head), self.window.reader.cursorRect(tail)

    def test_sentence_stepping_scrolls_the_reader_with_the_highlight(self):
        from src.study import sentence_ranges

        self.window.reader.setMaximumWidth(560)
        self.window.reader.resize(560, 240)
        self.application.processEvents()
        sentences = sentence_ranges(self.window.reader.toPlainText())
        self.assertGreater(len(sentences), 6)
        bar = self.window.reader.verticalScrollBar()
        self.assertGreater(bar.maximum(), 2 * self.window.reader.viewport().height(),
                           "the article must overflow the reader for this test to mean anything")

        caret = self.window.reader.textCursor()
        caret.setPosition(0)
        self.window.reader.setTextCursor(caret)
        bar.setValue(0)
        self.application.processEvents()

        offscreen, positions = [], []
        with patch.object(self.window, "_speak_system"):
            self.window.keyboard_sentence_step(1)
            self.application.processEvents()
            for _ in range(len(sentences)):
                index = self.window._sentence_index
                head, tail = self.sentence_viewport_band(*sentences[index][:2])
                if head.top() < -1 or tail.bottom() > self.window.reader.viewport().height() + 1:
                    offscreen.append((index, head.top(), tail.bottom()))
                positions.append(bar.value())
                self.window.keyboard_sentence_step(1)
                self.application.processEvents()
                if self.window._sentence_index == index:
                    break

        self.assertEqual(offscreen, [], "every played sentence must be inside the viewport")
        self.assertEqual(positions, sorted(positions), "the reader must only march forwards")
        self.assertGreater(positions[-1], bar.maximum() // 2, "the reader must follow the highlight to the end")
        self.window.cancel_sentence_sequence()

    def test_left_and_right_keys_request_a_sentence_repeat(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        repeats = []
        self.window.reader.sentence_repeat_requested.connect(lambda: repeats.append(1))
        with patch.object(self.window, "_speak_system"):
            QTest.keyClick(self.window.reader, Qt.Key.Key_Right)
            QTest.keyClick(self.window.reader, Qt.Key.Key_Left)
        self.assertEqual(repeats, [1, 1])

        caret = self.window.reader.textCursor()
        caret.setPosition(0)
        self.window.reader.setTextCursor(caret)
        # Ctrl/Shift + ←/→ go back to QTextEdit (Ctrl+←/→ still jumps a word). The offscreen
        # platform cannot move a caret by key, so assert only that we do not swallow them.
        with patch.object(self.window, "_speak_system"):
            QTest.keyClick(self.window.reader, Qt.Key.Key_Right, Qt.KeyboardModifier.ControlModifier)
            QTest.keyClick(self.window.reader, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(repeats, [1, 1], "modified arrows keep their normal behaviour")
        self.window.cancel_sentence_sequence()

    def seed_vocabulary_book(self):
        """Two prefixed articles plus the seeded one, each with one saved word."""
        from src.vocabulary import AUTO_LISTENING, AUTO_READING

        listening = self.repository.create_article("听力:非洲简界智能手机", "These devices are genuinely cheap.")
        reading = self.repository.create_article("阅读:在线课程的局限", "Online classes are compatible with busy schedules.")
        plain = [article for article in self.repository.list_articles() if article["title"] == "Online Classes"][0]["id"]
        for article_id, word in ((listening, "genuinely"), (reading, "compatible"), (plain, "infrequent")):
            text = self.repository.get_article(article_id)["text"]
            start = text.index(word)
            self.repository.add_vocabulary(article_id, start, start + len(word), word, "释义-" + word)
        self.window.refresh_vocabulary()
        return AUTO_LISTENING, AUTO_READING

    def vocabulary_rows(self):
        return [self.window.vocabulary_list.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(self.window.vocabulary_list.count())]

    def test_vocabulary_book_groups_words_by_article_title(self):
        auto_listening, auto_reading = self.seed_vocabulary_book()
        labels = [self.window.vocabulary_filter.itemText(index)
                  for index in range(self.window.vocabulary_filter.count())]
        self.assertEqual(labels[0], "全部分类（3）")
        self.assertIn("听力（1）", labels)
        self.assertIn("阅读（1）", labels)
        self.assertIn("未分类（1）", labels)
        self.assertEqual({record["word"]: record["category"] for record in self.vocabulary_rows()},
                         {"genuinely": auto_listening, "compatible": auto_reading, "infrequent": ""})
        self.assertTrue(any("[听力]" in self.window.vocabulary_list.item(row).text()
                            for row in range(self.window.vocabulary_list.count())))

        self.window.vocabulary_filter.setCurrentIndex(self.window.vocabulary_filter.findData(auto_listening))
        self.application.processEvents()
        self.assertEqual([record["word"] for record in self.vocabulary_rows()], ["genuinely"])
        self.assertIn("共 3 条生词 · 听力 1 条", self.window.vocabulary_count.text())

    def test_vocabulary_category_menu_moves_words_and_back_to_auto(self):
        self.seed_vocabulary_book()
        categories = self.window._vocabulary_categories()
        custom = categories.create("必背")
        self.window.vocabulary_filter.setCurrentIndex(0)
        self.application.processEvents()
        self.window.vocabulary_list.clearSelection()
        for row in range(self.window.vocabulary_list.count()):
            item = self.window.vocabulary_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole)["word"] == "genuinely":
                item.setSelected(True)
        self.window.apply_vocabulary_category(custom, self.window.vocabulary_list.selectedItems())
        self.application.processEvents()
        moved = [record for record in self.vocabulary_rows() if record["word"] == "genuinely"][0]
        self.assertEqual((moved["category"], moved["category_name"]), (custom, "必背"))
        self.assertIn("必背（1）", [self.window.vocabulary_filter.itemText(index)
                                    for index in range(self.window.vocabulary_filter.count())])

        # 恢复自动分类：标题规则重新接管，这条词又回到“听力”
        item = [self.window.vocabulary_list.item(row) for row in range(self.window.vocabulary_list.count())
                if self.window.vocabulary_list.item(row).data(Qt.ItemDataRole.UserRole)["word"] == "genuinely"][0]
        self.window.apply_vocabulary_category("", [item])
        self.application.processEvents()
        restored = [record for record in self.vocabulary_rows() if record["word"] == "genuinely"][0]
        self.assertEqual(restored["category"], "vgroup:auto:listening")

    def test_clicking_a_vocabulary_entry_reads_the_word(self):
        self.seed_vocabulary_book()
        spoken = []
        with patch.object(self.window, "_speak", side_effect=lambda text: spoken.append(text)):
            self.window.vocabulary_list.itemClicked.emit(self.window.vocabulary_list.item(0))
            self.window.speak_vocabulary_word(self.window.vocabulary_list.item(1))
            self.window.vocabulary_list.setCurrentRow(2)
            self.window.speak_vocabulary_word()
        self.assertEqual(len(spoken), 3)
        self.assertEqual(spoken[0], self.vocabulary_rows()[0]["word"])

    def test_vocabulary_delete_removes_rows_and_lets_the_phone_drop_them(self):
        from PySide6.QtTest import QTest

        self.seed_vocabulary_book()
        revision_before = self.repository.sync_revision()
        self.window.vocabulary_list.clearSelection()
        for row in range(self.window.vocabulary_list.count()):
            item = self.window.vocabulary_list.item(row)
            if item.data(Qt.ItemDataRole.UserRole)["word"] in ("genuinely", "compatible"):
                item.setSelected(True)
        with patch("src.main.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.window.delete_selected_vocabulary()
        self.application.processEvents()
        self.assertEqual({record["word"] for record in self.repository.list_vocabulary()}, {"infrequent"})
        self.assertGreater(self.repository.sync_revision(), revision_before,
                           "the deletion must bump the sync revision so phones drop the word")

        # Delete key on the list asks for removal of what is selected
        remaining = self.window.vocabulary_list.item(0)
        self.window.vocabulary_list.clearSelection()
        remaining.setSelected(True)
        requests = []
        self.window.vocabulary_list.delete_requested.connect(lambda: requests.append(1))
        with patch("src.main.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            QTest.keyClick(self.window.vocabulary_list, Qt.Key.Key_Delete)
        self.assertEqual(requests, [1])
        self.assertEqual(self.repository.list_vocabulary(), [])

    def test_builtin_categories_are_protected_in_the_ui(self):
        self.seed_vocabulary_book()
        hints = []
        with patch.object(self.window, "_show_hint", side_effect=lambda text: hints.append(text)), \
                patch("src.main.QInputDialog.getText", return_value=("跳过", True)), \
                patch("src.main.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.window.vocabulary_filter.setCurrentIndex(self.window.vocabulary_filter.findData("vgroup:auto:reading"))
            self.application.processEvents()
            self.window.rename_vocabulary_category()
            self.window.delete_vocabulary_category()
        self.assertEqual(hints, ["“听力”和“阅读”是内置分类，不能改名。", "“听力”和“阅读”是内置分类，不能删除。"])
        self.assertIn("vgroup:auto:reading", self.window._vocabulary_categories().all())

    def test_vocabulary_export_follows_the_category_filter(self):
        import csv as csv_module

        self.seed_vocabulary_book()
        auto_listening = "vgroup:auto:listening"
        self.window.vocabulary_filter.setCurrentIndex(self.window.vocabulary_filter.findData(auto_listening))
        self.application.processEvents()
        destination = self.root / "words.csv"
        with patch("src.main.QFileDialog.getSaveFileName", return_value=(str(destination), "")), \
                patch("src.main.QMessageBox.information"):
            self.window.export_vocabulary()
        with destination.open("r", encoding="utf-8-sig", newline="") as handle:
            exported = list(csv_module.DictReader(handle))
        self.assertEqual([row["单词"] for row in exported], ["genuinely"])
        self.assertEqual(exported[0]["分类"], "听力")

    def test_vocabulary_entry_dialog_collects_and_locks_fields(self):
        from src.main import VocabularyEntryDialog

        categories = self.window._vocabulary_categories()
        custom = categories.create("必背")
        dialog = VocabularyEntryDialog(None, categories.all(), self.window.vocabulary_dialog)
        dialog.word_input.setText("  put   off ")
        dialog.definition_input.setPlainText("推迟")
        dialog.context_input.setPlainText("The match was put off.")
        dialog.category_box.setCurrentIndex(dialog.category_box.findData(custom))
        self.assertEqual(dialog.values(), {"word": "put off", "definition": "推迟",
                                           "context": "The match was put off.", "category": custom})
        self.assertTrue(dialog.word_input.isEnabled())
        self.assertEqual(dialog.category_box.itemText(0), "自动（按文章标题）")

        article_entry = {"id": 1, "word": "compatible", "definition": "能共处的", "context": "",
                         "article_title": "阅读:课程局限", "article_id": 1, "manual": 0, "category": ""}
        bound = VocabularyEntryDialog(article_entry, categories.all(), self.window.vocabulary_dialog)
        self.assertFalse(bound.word_input.isEnabled(), "文章词条的文字与划线位置绑定")
        manual_entry = dict(article_entry, manual=1, article_id=None, word="take over")
        free = VocabularyEntryDialog(manual_entry, categories.all(), self.window.vocabulary_dialog)
        self.assertTrue(free.word_input.isEnabled())
        self.assertEqual(free.word_input.text(), "take over")

    def test_adding_a_hand_written_phrase_to_the_vocabulary_book(self):
        from src.main import VocabularyEntryDialog

        categories = self.window._vocabulary_categories()
        custom = categories.create("必背")
        values = {"word": "in demand", "definition": "有需求的", "context": "Jobs are in demand.", "category": custom}
        with patch.object(VocabularyEntryDialog, "values", return_value=values), \
                patch.object(VocabularyEntryDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            self.window.add_vocabulary_entry()
        self.application.processEvents()
        saved = [entry for entry in self.repository.list_vocabulary() if entry["manual"]]
        self.assertEqual([entry["word"] for entry in saved], ["in demand"])
        listed = [record for record in self.window.vocabulary_records() if record["word"] == "in demand"][0]
        self.assertEqual((listed["category"], listed["category_name"]), (custom, "必背"))
        self.assertTrue(any("✎ in demand" in self.window.vocabulary_list.item(row).text()
                            for row in range(self.window.vocabulary_list.count())))
        self.assertEqual(self.window.vocabulary_list.currentItem().data(Qt.ItemDataRole.UserRole)["word"], "in demand")
        self.assertIn("已加入词条", self.window.status_label.text())

        warnings = []
        with patch.object(VocabularyEntryDialog, "values", return_value=values), \
                patch.object(VocabularyEntryDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
                patch("src.main.QMessageBox.warning", side_effect=lambda *args: warnings.append(args[2])):
            self.window.add_vocabulary_entry()
        self.assertEqual(warnings, ["“in demand”已经在生词本里了"])
        self.assertEqual(len([entry for entry in self.repository.list_vocabulary() if entry["manual"]]), 1)

        with patch.object(VocabularyEntryDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.window.add_vocabulary_entry()
        self.assertEqual(len([entry for entry in self.repository.list_vocabulary() if entry["manual"]]), 1)

    def test_editing_a_manual_entry_moves_its_category_with_the_wording(self):
        from src.main import VocabularyEntryDialog

        categories = self.window._vocabulary_categories()
        custom = categories.create("必背")
        vocabulary_id = self.repository.add_manual_vocabulary("take over", "接管")
        categories.assign("take over", custom)
        self.window.refresh_vocabulary()
        widget = [self.window.vocabulary_list.item(row) for row in range(self.window.vocabulary_list.count())
                  if self.window.vocabulary_list.item(row).data(Qt.ItemDataRole.UserRole)["id"] == vocabulary_id][0]

        values = {"word": "take over sb", "definition": "接管某人", "context": "He took over the team.", "category": ""}
        with patch.object(VocabularyEntryDialog, "values", return_value=values), \
                patch.object(VocabularyEntryDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            self.window.edit_vocabulary_entry(widget)
        self.application.processEvents()
        renamed = [entry for entry in self.repository.list_vocabulary() if entry["manual"]][0]
        self.assertEqual((renamed["word"], renamed["definition"]), ("take over sb", "接管某人"))
        self.assertEqual(categories.manual("take over"), "", "旧写法上的分类记录要一起搬走")
        self.assertEqual(categories.manual("take over sb"), custom, "没改分类就沿用原来的")
        listed = [record for record in self.window.vocabulary_records() if record["word"] == "take over sb"][0]
        self.assertEqual(listed["category_name"], "必背")

    def test_a_phrase_selection_can_be_saved_as_a_vocabulary_word(self):
        article = self.repository.list_articles()[0]
        phrase = "Online classes"
        start = article["text"].index(phrase)
        # 拖选时多带了后面的空格：位置要收到词组本身，否则与原文对不上
        cursor = self.window.reader.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(start + len(phrase) + 1, QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)

        with patch("src.main.cached_translation", return_value="在线课程"):
            self.window.lookup_selection()
            self.window.save_vocabulary()

        saved = self.repository.list_vocabulary()
        self.assertEqual([entry["word"] for entry in saved], [phrase])
        self.assertEqual(saved[0]["start"], start)
        self.assertEqual(saved[0]["end"], start + len(phrase))
        self.assertEqual(saved[0]["definition"], "在线课程")
        self.assertIn(phrase, saved[0]["context"])
        self.assertIn("已将 Online classes 加入生词表", self.window.status_label.text())

    def test_a_phrase_selection_can_be_underlined(self):
        article = self.repository.list_articles()[0]
        phrase = "Online classes"
        start = article["text"].index(phrase)
        cursor = self.window.reader.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(start + len(phrase), QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)
        self.window.toggle_underline()
        marks = self.repository.list_annotations(article["id"])
        self.assertEqual([(mark["start"], mark["end"], mark["word"]) for mark in marks],
                         [(start, start + len(phrase), phrase)])

    def test_a_sentence_selection_is_still_rejected_with_a_helpful_hint(self):
        import re

        article = self.repository.list_articles()[0]
        first_line = article["text"].split("\n")[0]
        long_phrase = re.match(r"\S+(?:\s+\S+){7}", first_line).group(0)
        cursor = self.window.reader.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(len(long_phrase), QTextCursor.MoveMode.KeepAnchor)
        self.window.reader.setTextCursor(cursor)
        hints = []
        with patch.object(self.window, "_show_hint", side_effect=lambda text: hints.append(text)):
            self.window.save_vocabulary()
        self.assertEqual(len(hints), 1)
        self.assertIn("最多 6 个词的词组", hints[0])
        self.assertIn("收藏句段", hints[0])
        self.assertEqual(self.repository.list_vocabulary(), [])

    def test_number_keys_switch_the_reading_speed(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest

        self.window.audio_speed = 1.0
        QTest.keyClick(self.window.reader, Qt.Key.Key_2)
        self.assertEqual(self.window.audio_speed, 0.75)
        self.assertAlmostEqual(float(self.window.audio_settings.value("speed")), 0.75)
        self.assertIn("已切换 0.75 倍速", self.window.status_label.text())

        QTest.keyClick(self.window.reader, Qt.Key.Key_1)
        self.assertEqual(self.window.audio_speed, 1.0)
        self.assertAlmostEqual(float(self.window.audio_settings.value("speed")), 1.0)
        self.assertIn("已切换 1 倍速", self.window.status_label.text())

        # 已经是这个速度时只提示，不重复写设置
        self.window.audio_settings.sync()
        QTest.keyClick(self.window.reader, Qt.Key.Key_1)
        self.assertIn("当前已是 1 倍速", self.window.status_label.text())

        # 带修饰键的数字仍归原功能，不改语速
        QTest.keyClick(self.window.reader, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.window.audio_speed, 1.0)

    def test_audio_button_is_a_plain_speed_toggle_without_a_dialog(self):
        from PySide6.QtWidgets import QToolButton

        button = self.window.audio_settings_button
        self.assertIsInstance(button, QToolButton)
        self.assertGreaterEqual(button.minimumHeight(), 44)
        self.assertGreaterEqual(button.minimumWidth(), 100)

        opened = []
        self.window.audio_speed = 1.0
        self.window._refresh_audio_button_text()
        self.assertIn("🔊 1 倍速", button.text(), "按钮上直接写着当前倍速")
        with patch("src.main.QDialog.exec", side_effect=lambda *args: opened.append(1) or 0):
            button.click()
            self.assertEqual(self.window.audio_speed, 0.75)
            self.assertIn("🔊 0.75 倍速", button.text())
            button.click()
            self.assertEqual(self.window.audio_speed, 1.0)
            self.assertIn("🔊 1 倍速", button.text())
        self.assertEqual(opened, [], "单击不再弹出发音与语速窗口")
        self.assertAlmostEqual(float(self.window.audio_settings.value("speed")), 1.0)
        self.assertIn("已切换 1 倍速", self.window.status_label.text())

        # 对话框里选的其它倍速（0.6／0.9／1.25）点一下先回到 0.75，不会跳到别的档位
        for start in (0.6, 0.9, 1.25):
            self.window.audio_speed = start
            button.click()
            self.assertEqual(self.window.audio_speed, 0.75, f"{start} 倍速点一下应为 0.75")

        menus = [child.menu() for child in self.window.findChildren(QToolButton) if child.menu()]
        entries = [action.text() for menu in menus for action in menu.actions()]
        self.assertNotIn("发音设置", entries, "原来藏在朗读菜单里的入口已拆出来")
        self.assertIn("▶ 朗读全文", entries)

    def test_audio_button_right_click_still_opens_the_dialog(self):
        from PySide6.QtCore import QPoint, Qt

        button = self.window.audio_settings_button
        self.assertEqual(button.contextMenuPolicy(), Qt.ContextMenuPolicy.CustomContextMenu)
        opened = []
        with patch.object(self.window, "open_audio_settings", side_effect=lambda: opened.append(1)):
            button.customContextMenuRequested.emit(QPoint(8, 8))
        self.assertEqual(opened, [1], "右键仍可打开发音与语速设置")

    def test_keyboard_sentence_repeat_replays_without_stepping(self):
        from src.study import sentence_ranges

        sentences = sentence_ranges(self.window.reader.toPlainText())
        spoken = []
        self.window.cancel_sentence_sequence()
        with patch.object(self.window, "_speak_system", side_effect=lambda text: spoken.append(text)):
            self.window.play_sentence_at(0)
            index = self.window._sentence_index
            self.assertEqual(spoken, [sentences[index][2]])

            self.window.keyboard_sentence_repeat()
            self.assertEqual(self.window._sentence_index, index, "←/→ must stay on the current sentence")
            self.assertEqual(spoken, [sentences[index][2], sentences[index][2]])

            self.window.keyboard_sentence_step(1)
            stepped = self.window._sentence_index
            self.assertNotEqual(stepped, index)
            self.window.keyboard_sentence_repeat()
            self.assertEqual(self.window._sentence_index, stepped)
            self.assertEqual(spoken[-1], sentences[stepped][2])
            self.assertEqual(len(spoken), 4)

            # After the sequence ended, the key repeats the sentence under the caret.
            self.window.cancel_sentence_sequence()
            caret = self.window.reader.textCursor()
            caret.setPosition(sentences[3][0] + 1)
            self.window.reader.setTextCursor(caret)
            self.window.keyboard_sentence_repeat()
            self.assertEqual(self.window._sentence_index, 3)
            self.assertEqual(spoken[-1], sentences[3][2])
        self.window.cancel_sentence_sequence()


if __name__ == "__main__":
    unittest.main()

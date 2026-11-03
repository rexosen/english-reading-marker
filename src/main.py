from __future__ import annotations

import os
import sys
from pathlib import Path

_DLL_DIRECTORY_HANDLES = []
if getattr(sys, "frozen", False):
    for _dll_path in (
        Path(sys._MEIPASS) / "PySide6",
        Path(sys._MEIPASS) / "shiboken6",
        Path(sys._MEIPASS),
    ):
        if _dll_path.exists():
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(_dll_path)))

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, QLocale, QPoint, QTimer, QUrl, QSettings, QLockFile
from PySide6.QtTextToSpeech import QTextToSpeech
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtGui import QAction, QColor, QTextCharFormat, QTextCursor, QFont, QDesktopServices, QPainter, QImage
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QComboBox,
    QMenu,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QSizePolicy,
    QTextEdit,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.dictionary import DictionaryError, lookup_chinese, cached_translation
from src.domain import (
    find_selected_word,
    normalize_line_endings,
    normalize_article_text,
    python_offset_to_qt,
    qt_offset_to_python,
)
from src.exporter import export_vocabulary_csv
from src.repository import ReaderRepository
from src.storage import prepare_storage, backup_database, StorageError, data_directory
from src.study_ui import StudyUi
from src.lan_sync import LanSyncService
from src.pronunciation import pronunciation_file, PronunciationError, audio_word


APP_NAME = "英语阅读标记器"
SAMPLE_NAME = "Online_Classes_原文.txt"


class LookupSignals(QObject):
    finished = Signal(object, object, object)


class LookupWorker(QRunnable):
    def __init__(self, word: str, selection: tuple[int, int, str], request_id: int):
        super().__init__()
        self.word = word
        self.selection = selection
        self.request_id = request_id
        self.signals = LookupSignals()

    def run(self) -> None:
        try:
            result = lookup_chinese(self.word)
            self.signals.finished.emit(self.request_id, self.selection, result)
        except DictionaryError as error:
            self.signals.finished.emit(self.request_id, self.selection, error)


class WordAudioWorker(QRunnable):
    def __init__(self, text, accent, request_id):
        super().__init__()
        self.text, self.accent, self.request_id = text, accent, request_id
        self.signals = LookupSignals()

    def run(self):
        try:
            result = pronunciation_file(self.text, self.accent)
        except PronunciationError as error:
            result = error
        self.signals.finished.emit(self.request_id, self.text, result)


class ReadingTextEdit(QTextEdit):
    translate_requested = Signal(object)
    sentence_requested = Signal(int)

    def set_background_options(self, options):
        self._background_options = options
        self._background_image = QImage(str(options.get('image','')))
        self._scaled_background = None
        self.viewport().update()

    def paintEvent(self, event):
        options = getattr(self, '_background_options', {})
        painter = QPainter(self.viewport())
        painter.fillRect(self.viewport().rect(), QColor(options.get('background','#fff9ed')))
        image = getattr(self, '_background_image', QImage())
        if not image.isNull():
            if self._scaled_background is None or self._scaled_background[0] != self.viewport().size():
                self._scaled_background = (self.viewport().size(), image.scaled(self.viewport().size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            scaled = self._scaled_background[1]
            painter.setOpacity(int(options.get('opacity',22))/100)
            painter.drawImage((self.viewport().width()-scaled.width())//2,(self.viewport().height()-scaled.height())//2,scaled)
        painter.end()
        super().paintEvent(event)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.sentence_requested.emit(qt_offset_to_python(self.toPlainText(), self.cursorForPosition(event.position().toPoint()).position()))


    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            cursor = self.cursorForPosition(event.position().toPoint())
            existing = self.textCursor()
            self._right_anchor = cursor.position()
            self._right_moved = False
            if not (existing.hasSelection() and existing.selectionStart() <= cursor.position() < existing.selectionEnd()):
                cursor.select(QTextCursor.SelectionType.WordUnderCursor)
                self.setTextCursor(cursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.RightButton:
            cursor = self.cursorForPosition(event.position().toPoint())
            if abs(cursor.position() - self._right_anchor) > 1:
                self._right_moved = True
                end = cursor.position()
                cursor.setPosition(self._right_anchor)
                cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
                self.setTextCursor(cursor)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.translate_requested.emit(event.globalPosition().toPoint())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        # Right release already starts translation; suppress the standard edit menu.
        event.accept()


class TranslationView(QTextBrowser):
    """Scrollable plain text that never imposes the content's width on the layout."""
    def setText(self, text):
        self.setPlainText(text)

    def text(self):
        return self.toPlainText()


class ArticleEditorDialog(QDialog):
    def __init__(self, title: str = "", text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("添加文章")
        self.resize(760, 620)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(QLabel("文章名称"))
        self.title_input = QLineEdit(title)
        self.title_input.setPlaceholderText("例如：Online Classes")
        layout.addWidget(self.title_input)

        row = QHBoxLayout()
        row.addWidget(QLabel("文章正文"))
        row.addStretch(1)
        import_button = QPushButton("从 TXT 导入")
        import_button.clicked.connect(self.import_text)
        row.addWidget(import_button)
        layout.addLayout(row)

        self.body_input = QTextEdit()
        self.body_input.setPlaceholderText("粘贴转换后的文章文本，检查后保存……")
        self.body_input.setPlainText(normalize_line_endings(text))
        layout.addWidget(self.body_input, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)
        save_button = QPushButton("保存文章")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self.accept)
        buttons.addWidget(cancel_button)
        buttons.addWidget(save_button)
        layout.addLayout(buttons)

    def import_text(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入文本文章", str(Path.home()), "文本文件 (*.txt);;所有文件 (*)"
        )
        if not file_path:
            return
        path = Path(file_path)
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        if not self.title_input.text().strip():
            self.title_input.setText(path.stem)
        self.body_input.setPlainText(normalize_line_endings(text))

    def article(self) -> tuple[str, str]:
        return self.title_input.text().strip(), normalize_article_text(self.body_input.toPlainText())


class MainWindow(StudyUi, QMainWindow):
    def __init__(self, repository: ReaderRepository, sample_path: Path, *, seed_sample: bool = True):
        super().__init__()
        self.repository = repository
        self.sample_path = sample_path
        self.thread_pool = QThreadPool.globalInstance()
        self.current_article_id: int | None = None
        self.current_selection: tuple[int, int, str] | None = None
        self.current_definition = ""
        self.definition_selection: tuple[int, int, str] | None = None
        self.lookup_request_id = 0
        self.translation_popup = None
        self.sync_service = None
        self._sync_revision = repository.sync_revision()
        self._loading_article = False
        self.speech = QTextToSpeech("sapi", self)
        self.speech.setLocale(QLocale("en_US"))
        self.audio_settings = QSettings(str(repository.database_path.parent / "audio.ini"), QSettings.Format.IniFormat)
        self.audio_accent = self.audio_settings.value("accent", "us")
        self.audio_speed = float(self.audio_settings.value("speed", 0.75))
        self.audio_source = self.audio_settings.value("source", "dictionary")
        self.audio_request_id = 0
        self.word_player = QMediaPlayer(self)
        self.word_output = QAudioOutput(self)
        self.word_player.setAudioOutput(self.word_output)
        self.word_output.setVolume(0.9)
        if hasattr(self.word_player, "setPitchCompensation"):
            self.word_player.setPitchCompensation(True)
        self.word_player.errorOccurred.connect(self._word_audio_failed)
        self._audio_text = ""
        self.speech.setRate((self.audio_speed - 1) * 1.2)
        self.speech.errorOccurred.connect(lambda *args: self._show_hint("朗读失败：" + self.speech.errorString()))

        self.setWindowTitle(APP_NAME)
        self.resize(1420, 900)
        self.setMinimumSize(1080, 720)
        self.setStyleSheet(self._style_sheet())
        self._build_ui()
        self.init_study_ui()
        self.menuBar().addAction("数据与备份", self.open_backup_manager)
        if seed_sample:
            self._seed_sample_if_empty()
        self.refresh_articles()
        self.refresh_vocabulary()
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(1500)
        self.sync_timer.timeout.connect(self.refresh_from_sync)
        self.sync_timer.start()
        self.progress_timer = QTimer(self)
        self.progress_timer.setSingleShot(True)
        self.progress_timer.setInterval(500)
        self.progress_timer.timeout.connect(self.save_reading_progress)
        self.reader.verticalScrollBar().valueChanged.connect(lambda: self.progress_timer.start() if not self._loading_article else None)

    @staticmethod
    def _style_sheet() -> str:
        return """
        QWidget { color: #203044; font-family: "Microsoft YaHei UI"; font-size: 10pt; }
        QMainWindow, QWidget#root { background: #f4f6fa; }
        QLabel#brand { color: #66758b; font-size: 9pt; font-weight: 700; letter-spacing: 1px; }
        QLabel#pageTitle { color: #17283e; font-size: 21pt; font-weight: 700; }
        QLabel#sectionTitle { color: #203044; font-size: 12pt; font-weight: 700; }
        QLabel#muted { color: #78869a; }
        QFrame#panel { background: white; border: 1px solid #e5eaf1; border-radius: 14px; }
        QListWidget { background: transparent; border: 0; outline: 0; padding: 4px; }
        QListWidget::item { padding: 12px 10px; border-radius: 8px; margin: 2px 0; }
        QListWidget::item:selected { background: #e9f0ff; color: #2558b8; }
        QListWidget::item:hover { background: #f1f5fb; }
        QTextEdit { background: #fff; border: 1px solid #e5eaf1; border-radius: 12px; padding: 22px; selection-background-color: #cfe0ff; font-family: "Georgia", "Times New Roman"; font-size: 14pt; line-height: 1.7; }
        QPushButton, QToolButton { background: #f2f5fa; border: 1px solid #e2e8f1; border-radius: 8px; padding: 9px 13px; }
        QPushButton:hover, QToolButton:hover { background: #e9eef6; }
        QPushButton#primaryButton { background: #315fbd; color: white; border: 0; font-weight: 700; }
        QPushButton#primaryButton:hover { background: #264f9f; }
        QLineEdit { padding: 10px; border: 1px solid #dfe5ed; border-radius: 8px; background: white; }
        QLabel#definition { color: #244a93; font-size: 14pt; font-weight: 700; }
        """

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 8, 16, 12)
        outer.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("英语阅读标记器")
        title.setStyleSheet("font-size: 16pt; font-weight: 700;")
        header.addWidget(title)
        header.addStretch(1)
        paste_button = QPushButton("＋  粘贴文章")
        paste_button.clicked.connect(self.add_pasted_article)
        import_button = QPushButton("导入 TXT")
        import_button.clicked.connect(self.add_text_file)
        export_button = QPushButton("生词本")
        export_button.setObjectName("primaryButton")
        export_button.clicked.connect(self.open_vocabulary)
        self.sync_button = QPushButton("手机同步")
        self.sync_button.clicked.connect(self.open_sync_dialog)
        header.addWidget(self.sync_button)
        header.addWidget(paste_button)
        header.addWidget(import_button)
        header.addWidget(export_button)
        outer.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.reader_splitter = splitter
        outer.addWidget(splitter, 1)

        left_panel = self._panel()
        left_panel.setMinimumWidth(180)
        left_panel.setMaximumWidth(240)
        self.library_panel = left_panel
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(15, 18, 15, 15)
        left_layout.addWidget(self._section_label("我的文章"))
        self.add_library_controls(left_layout)
        self.article_list = QListWidget()
        self.article_list.currentItemChanged.connect(self._on_article_changed)
        self.article_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.article_list.customContextMenuRequested.connect(self.show_article_menu)
        left_layout.addWidget(self.article_list, 1)
        splitter.addWidget(left_panel)

        reader_panel = self._panel()
        reader_panel.setMinimumWidth(520)
        reader_layout = QVBoxLayout(reader_panel)
        reader_layout.setContentsMargins(12, 10, 12, 10)
        reader_layout.setSpacing(6)
        reader_header = QHBoxLayout()
        reader_titles = QVBoxLayout()
        self.article_title_label = QLabel("选择一篇文章")
        self.article_title_label.setObjectName("sectionTitle")
        self.article_title_label.setWordWrap(True)
        self.article_title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.article_subtitle_label = QLabel("右键单词直接查词；选中句子或段落后右键翻译。")
        self.article_subtitle_label.setObjectName("muted")
        reader_titles.addWidget(self.article_title_label)
        self.article_subtitle_label.hide()
        reader_header.addLayout(reader_titles, 1)
        reader_layout.addLayout(reader_header)

        actions = QHBoxLayout()
        self.lookup_button = QToolButton()
        self.lookup_button.setText("翻译所选")
        self.lookup_button.clicked.connect(self.lookup_selection)
        self.underline_button = QToolButton()
        self.underline_button.setText("划线")
        self.underline_button.setToolTip("划线 / 取消划线")
        self.underline_button.clicked.connect(self.toggle_underline)
        self.save_word_button = QToolButton()
        self.save_word_button.setText("＋ 生词")
        self.save_word_button.clicked.connect(self.save_vocabulary)
        actions.addWidget(self.lookup_button)
        actions.addWidget(self.underline_button)
        actions.addWidget(self.save_word_button)
        def action_menu(caption, entries):
            button = QToolButton()
            button.setText(caption)
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(button)
            for text, callback in entries:
                menu.addAction(text, callback)
            button.setMenu(menu)
            actions.addWidget(button)
            return menu

        speech_menu = action_menu("朗读", [
            ("▶ 朗读所选", self.speak_selection),
            ("▶ 朗读全文", self.speak_article),
            ("暂停 / 继续", self.pause_speech),
            ("停止朗读", self.stop_audio),
            ("发音设置", self.open_audio_settings),
        ])
        action_menu("学习", [
            ("收藏所选句段", self.save_selected_note),
            ("句子收藏与笔记", self.open_notes),
            ("生词复习", self.open_review),
        ])
        action_menu("设置", [("阅读显示与背景", self.open_display)])
        actions.addStretch(1)
        self.focus_button = QToolButton()
        self.focus_button.setText("专注阅读")
        self.focus_button.setCheckable(True)
        self.focus_button.toggled.connect(self.toggle_focus_reading)
        actions.addWidget(self.focus_button)
        reader_layout.addLayout(actions)
        self.add_study_controls(reader_layout)
        sentence_action = speech_menu.addAction("显示逐句控制")
        sentence_action.setCheckable(True)
        sentence_action.toggled.connect(self.sentence_controls.setVisible)

        self.reader = ReadingTextEdit()
        self.reader.translate_requested.connect(self.show_translation_popup)
        self.reader.setReadOnly(True)
        self.reader.setPlaceholderText("从左侧选择文章，或新建一篇文章。")
        self.reader.setFont(QFont("Georgia", 14))
        # A centered widget uses its sizeHint instead of filling the row. Give
        # the editor the horizontal stretch; spacers center it only at its cap.
        self.reader.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        reading_row = QHBoxLayout()
        reading_row.setContentsMargins(0, 0, 0, 0)
        reading_row.setSpacing(0)
        reading_row.addStretch(0)
        reading_row.addWidget(self.reader, 1)
        reading_row.addStretch(0)
        reader_layout.addLayout(reading_row, 1)
        self.status_label = QLabel("文章与标记仅保存在此电脑。")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        reader_layout.addWidget(self.status_label)
        splitter.addWidget(reader_panel)

        right_panel = self._panel()
        right_panel.setMinimumWidth(220)
        right_panel.setMaximumWidth(280)
        self.translation_panel = right_panel
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 18, 16, 15)
        right_layout.addWidget(self._section_label("翻译助手"))
        self.selected_word_label = QLabel("尚未选择单词")
        self.selected_word_label.setObjectName("definition")
        self.selected_word_label.setWordWrap(True)
        self.selected_word_label.setMinimumWidth(0)
        self.selected_word_label.setMaximumHeight(110)
        self.selected_word_label.setTextFormat(Qt.TextFormat.PlainText)
        self.selected_word_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.definition_label = TranslationView()
        self.definition_label.setText("右键单词查看释义；先拖选内容再右键，可翻译整句或整段。")
        self.definition_label.setMinimumWidth(0)
        self.definition_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.definition_label.setStyleSheet('font-family: "Microsoft YaHei UI"; font-size: 11pt; padding: 8px; border: 0;')
        self.definition_label.setObjectName("muted")
        right_layout.addWidget(self.selected_word_label)
        right_layout.addWidget(self.definition_label, 1)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([200, 1000, 240])
        self._build_vocabulary_window()

        add_action = QAction("添加文章", self)
        add_action.setShortcut("Ctrl+N")
        add_action.triggered.connect(self.add_pasted_article)
        self.addAction(add_action)

    def toggle_focus_reading(self, enabled):
        self.library_panel.setVisible(not enabled)
        self.translation_panel.setVisible(not enabled)
        self.focus_button.setText("退出专注" if enabled else "专注阅读")

    def open_sync_dialog(self):
        if not hasattr(self, "sync_dialog"):
            self.sync_dialog = QDialog(self)
            self.sync_dialog.setWindowTitle("手机局域网同步")
            self.sync_dialog.resize(600, 430)
            layout = QVBoxLayout(self.sync_dialog)
            note = QLabel("手机和电脑连接同一个 Wi-Fi 或路由器。电脑保持开机，阅读器保持运行。")
            note.setWordWrap(True)
            layout.addWidget(note)
            self.sync_info = QTextBrowser()
            self.sync_info.setStyleSheet('font-family: "Microsoft YaHei UI"; font-size: 12pt;')
            layout.addWidget(self.sync_info)
            pair_button = QPushButton("开启同步 / 生成一次性配对码")
            pair_button.clicked.connect(self.enable_sync_pairing)
            layout.addWidget(pair_button)
            stop_button = QPushButton("停止局域网同步")
            stop_button.clicked.connect(self.stop_sync)
            layout.addWidget(stop_button)
            self.sync_info.setPlainText("点击下方按钮开启同步。在安卓 App 的“连接电脑”中填写这里显示的地址与配对码。")
        self.sync_dialog.show()
        self.sync_dialog.raise_()
        self.sync_dialog.activateWindow()

    def enable_sync_pairing(self):
        try:
            if self.sync_service is None:
                self.sync_service = LanSyncService(self.repository.database_path, Path(sys.executable).parent / "EnglishReader_Android_v1.apk" if getattr(sys, "frozen", False) else None)
            try:
                self.sync_service.start()
            except OSError:
                self.sync_service.start(port=0)
            code = self.sync_service.new_pairing_code()
            addresses = self.sync_service.addresses()
            self.sync_info.setPlainText(
                "同步已开启\n先在手机浏览器打开以下地址，可下载安卓安装包。安装后进入 App 配对。\n\n电脑地址（选择与手机网络对应的一项）：\n" +
                "\n".join(addresses or ["未检测到局域网地址，请检查网络连接。"] ) +
                f"\n\n一次性配对码：{code}\n10 分钟内有效，成功配对一次后失效。\n\n已配对手机以后会自动重连。若 Windows 弹出网络访问提示，请由你允许家庭/专用网络访问。"
            )
            self.sync_button.setText("手机同步 · 已开启")
        except (OSError, RuntimeError) as error:
            self.sync_info.setPlainText("开启失败：" + str(error))

    def stop_sync(self):
        if self.sync_service:
            self.sync_service.stop()
        self.sync_info.setPlainText("局域网同步已停止。手机离线修改会留在手机上，重新开启服务后可补同步。")
        self.sync_button.setText("手机同步")

    def save_reading_progress(self):
        if self.current_article_id is not None and not self._loading_article:
            position = self.reader.cursorForPosition(QPoint(5, 5)).position()
            offset = qt_offset_to_python(self.reader.toPlainText(), position)
            self.repository.save_progress(self.current_article_id, offset)

    def refresh_from_sync(self):
        revision = self.repository.sync_revision()
        if revision == self._sync_revision:
            return
        self._sync_revision = revision
        self._loading_article = True
        try:
            self.refresh_group_filter()
            active_id = self.current_article_id
            cursor = self.reader.textCursor()
            scroll = self.reader.verticalScrollBar().value()
            self.article_list.blockSignals(True)
            self.article_list.clear()
            for article in self.filtered_articles():
                item = QListWidgetItem(self.article_caption(article))
                item.setToolTip(article["title"])
                item.setData(Qt.ItemDataRole.UserRole, article["id"])
                self.article_list.addItem(item)
                if article["id"] == active_id:
                    self.article_list.setCurrentItem(item)
                    self.article_title_label.setText(article["title"])
            self.article_list.blockSignals(False)
            if active_id is not None:
                clear_cursor = QTextCursor(self.reader.document())
                clear_cursor.select(QTextCursor.SelectionType.Document)
                fmt = QTextCharFormat()
                fmt.setFontUnderline(False)
                clear_cursor.mergeCharFormat(fmt)
                self._apply_annotations(active_id)
                self.reader.setTextCursor(cursor)
                self.reader.verticalScrollBar().setValue(scroll)
            elif self.article_list.count():
                self.article_list.setCurrentRow(0)
            self.refresh_vocabulary()
        finally:
            self._loading_article = False

    def _build_vocabulary_window(self):
        self.vocabulary_dialog = QDialog(self)
        self.vocabulary_dialog.setWindowTitle("生词本 · 英语阅读标记器")
        self.vocabulary_dialog.resize(760, 600)
        self.vocabulary_dialog.setMinimumSize(500, 400)
        layout = QVBoxLayout(self.vocabulary_dialog)
        header = QHBoxLayout()
        header.addWidget(self._section_label("我的生词本"))
        header.addStretch(1)
        export = QPushButton("导出 CSV")
        export.setObjectName("primaryButton")
        export.clicked.connect(self.export_vocabulary)
        header.addWidget(export)
        layout.addLayout(header)
        self.vocabulary_count = QLabel()
        layout.addWidget(self.vocabulary_count)
        self.vocabulary_list = QListWidget()
        self.vocabulary_list.setWordWrap(True)
        self.vocabulary_list.currentItemChanged.connect(self._show_vocabulary_context)
        layout.addWidget(self.vocabulary_list, 2)
        self.vocabulary_context = QTextBrowser()
        self.vocabulary_context.setPlaceholderText("选择生词，查看释义、来源文章和原句。")
        self.vocabulary_context.setStyleSheet('font-family: "Microsoft YaHei UI"; font-size: 11pt; padding: 10px;')
        layout.addWidget(self.vocabulary_context, 1)

    def open_vocabulary(self):
        self.refresh_vocabulary()
        self.vocabulary_dialog.show()
        self.vocabulary_dialog.raise_()
        self.vocabulary_dialog.activateWindow()

    def _show_vocabulary_context(self, current, previous):
        if not current:
            self.vocabulary_context.clear()
            return
        record = current.data(Qt.ItemDataRole.UserRole)
        self.vocabulary_context.setPlainText(
            f"{record['word']}\n{record['definition']}\n\n来源：{record['article_title']}\n{record['context']}"
        )

    @staticmethod
    def _panel() -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        return panel

    @staticmethod
    def _section_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    def _seed_sample_if_empty(self) -> None:
        if self.repository.list_articles() or not self.sample_path.exists():
            return
        text = self.sample_path.read_text(encoding="utf-8-sig")
        self.repository.create_article("Online Classes", text)

    def show_article_menu(self, position):
        item = self.article_list.itemAt(position)
        if item is None:
            return
        menu = QMenu(self.article_list)
        rename = menu.addAction("重命名")
        rename.triggered.connect(lambda: self.rename_article(item))
        article_id = int(item.data(Qt.ItemDataRole.UserRole))
        menu.addAction("移动到分组", lambda:self.assign_group(article_id))
        menu.addAction("取消置顶" if self.study.metadata(article_id)['pinned'] else "置顶", lambda:self.toggle_article_flag(article_id,'pinned'))
        menu.addAction("标为未读" if self.study.metadata(article_id)['read'] else "标为已读", lambda:self.toggle_article_flag(article_id,'read'))
        menu.exec(self.article_list.viewport().mapToGlobal(position))

    def rename_article(self, item):
        article_id = int(item.data(Qt.ItemDataRole.UserRole))
        title, accepted = QInputDialog.getText(
            self, "重命名文章", "文章名称：", QLineEdit.EchoMode.Normal, self.repository.get_article(article_id)["title"]
        )
        if not accepted:
            return
        try:
            self.repository.rename_article(article_id, title)
        except ValueError as error:
            self._show_hint(str(error))
            return
        title = title.strip()
        item.setText(title)
        item.setToolTip(title)
        if self.current_article_id == article_id:
            self.article_title_label.setText(title)
        self.refresh_vocabulary()
        self.refresh_articles(self.current_article_id)
        self.status_label.setText(f"文章已重命名为：{title}")

    def refresh_articles(self, select_id: int | None = None) -> None:
        if not hasattr(self, 'article_list'): return
        active = self.current_article_id
        self.article_list.blockSignals(True)
        self.article_list.clear()
        selected_item = None
        for article in self.filtered_articles():
            item = QListWidgetItem(self.article_caption(article))
            item.setData(Qt.ItemDataRole.UserRole, article["id"])
            item.setToolTip(article["title"])
            self.article_list.addItem(item)
            if article["id"] == select_id: selected_item = item
        if selected_item:
            self.article_list.setCurrentItem(selected_item)
        self.article_list.blockSignals(False)
        if selected_item:
            if active != select_id or not self.reader.toPlainText(): self._on_article_changed(selected_item, None)
            else: self.article_title_label.setText(self.repository.get_article(select_id)['title'])
        elif active is None and self.article_list.count():
            self.article_list.setCurrentRow(0)

    def refresh_vocabulary(self) -> None:
        self.vocabulary_list.clear()
        records = self.repository.list_vocabulary()
        self.vocabulary_count.setText(f"共 {len(records)} 条生词，选中条目可查看原句。" if records else "生词本为空。在阅读时右键查词，再点击“加入生词表”。")
        for record in records:
            item = QListWidgetItem(f"{record['word']}   ·   {record['definition'] or '暂无释义'}")
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(f"{record['article_title']}\n{record['context']}")
            self.vocabulary_list.addItem(item)

    def _on_article_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        article_id = int(current.data(Qt.ItemDataRole.UserRole))
        article = self.repository.get_article(article_id)
        if article is None:
            return
        self.lookup_request_id += 1
        self.stop_audio()
        if self.translation_popup:
            self.translation_popup.hide()
        self.current_article_id = article_id
        self.current_selection = None
        self.current_definition = ""
        self.definition_selection = None
        self.article_title_label.setText(article["title"])
        self._loading_article = True
        self.reader.setPlainText(article["text"])
        self._sentences = []
        self._sentence_index = 0
        self.apply_display()
        self._apply_annotations(article_id)
        offset = min(self.repository.get_progress(article_id), len(article["text"]))
        cursor = self.reader.textCursor()
        cursor.setPosition(python_offset_to_qt(article["text"], offset))
        self.reader.setTextCursor(cursor)
        self.reader.ensureCursorVisible()
        self._loading_article = False
        self.selected_word_label.setText("尚未选择单词")
        self.definition_label.setText("右键单词查看释义；先拖选内容再右键，可翻译整句或整段。")
        self.status_label.setText("右键查词 / 翻译；工具栏支持所选内容与全文朗读。")

    def _apply_annotations(self, article_id: int) -> None:
        original_cursor = self.reader.textCursor()
        article_text = self.reader.toPlainText()
        for annotation in self.repository.list_annotations(article_id):
            cursor = QTextCursor(self.reader.document())
            cursor.setPosition(python_offset_to_qt(article_text, annotation["start"]))
            cursor.setPosition(
                python_offset_to_qt(article_text, annotation["end"]),
                QTextCursor.MoveMode.KeepAnchor,
            )
            fmt = QTextCharFormat()
            fmt.setFontUnderline(True)
            fmt.setUnderlineColor(QColor("#d06a35"))
            cursor.mergeCharFormat(fmt)
        self.reader.setTextCursor(original_cursor)

    def _get_selection(self) -> tuple[int, int, str] | None:
        if self.current_article_id is None:
            self._show_hint("请先选择或添加一篇文章。")
            return None
        cursor = self.reader.textCursor()
        if not cursor.hasSelection():
            self._show_hint("请先在文章中选中一个英文单词。")
            return None
        article_text = self.reader.toPlainText()
        start = qt_offset_to_python(article_text, cursor.selectionStart())
        end = qt_offset_to_python(article_text, cursor.selectionEnd())
        selected = find_selected_word(article_text, start, end)
        if selected is None:
            self._show_hint("请只选择一个完整的英文单词。")
            return None
        if self.current_selection != selected:
            self.lookup_request_id += 1
            self.current_definition = ""
            self.definition_selection = None
            self.definition_label.setText("当前选中已更改，请重新查词。")
        self.current_selection = selected
        self.selected_word_label.setText(selected[2])
        return selected

    def _get_translation_selection(self):
        cursor = self.reader.textCursor()
        if not cursor.hasSelection():
            self._show_hint("请选中英文内容，或右键单词。")
            return None
        text = self.reader.toPlainText()
        start = qt_offset_to_python(text, cursor.selectionStart())
        end = qt_offset_to_python(text, cursor.selectionEnd())
        content = text[start:end].strip()
        if not content:
            return None
        return start, end, content

    def show_translation_popup(self, position):
        selected = self._get_translation_selection()
        if selected is None:
            return
        if self.translation_popup:
            self.translation_popup.close()
        popup = QFrame(self, Qt.WindowType.Popup)
        popup.setObjectName("panel")
        layout = QVBoxLayout(popup)
        self.popup_definition = QTextBrowser()
        self.popup_definition.setMinimumSize(390, 175)
        layout.addWidget(self.popup_definition)
        row = QHBoxLayout()
        for caption, callback in [("▶ 发音 / 朗读", self.speak_selection), ("划线", self.toggle_underline), ("加入生词表", self.save_vocabulary), ("收藏句段", self.save_selected_note)]:
            button = QPushButton(caption)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addLayout(row)
        popup.adjustSize()
        screen = QApplication.screenAt(position) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        popup.move(max(bounds.left(), min(position.x(), bounds.right() - popup.width())), max(bounds.top(), min(position.y(), bounds.bottom() - popup.height())))
        self.translation_popup = popup
        popup.show()
        self.lookup_selection()

    def _display_translation(self, text):
        self.definition_label.setText(text)
        if self.translation_popup and self.translation_popup.isVisible():
            self.popup_definition.setPlainText(text)

    def lookup_selection(self) -> None:
        selected = self._get_translation_selection()
        if selected is None:
            return
        self.lookup_request_id += 1
        request_id = self.lookup_request_id
        self.current_selection = selected
        self.selected_word_label.setText(selected[2][:80] + ("…" if len(selected[2]) > 80 else ""))
        self.current_definition = ""
        self.definition_selection = None
        cached = cached_translation(selected[2])
        if cached:
            self._on_lookup_finished(request_id, selected, cached)
            return
        self._display_translation("正在翻译所选内容……首次查询需要联网。")
        worker = LookupWorker(selected[2], selected, request_id)
        worker.signals.finished.connect(self._on_lookup_finished)
        self.thread_pool.start(worker)

    def speak_selection(self):
        selected = self._get_translation_selection()
        if selected:
            self._speak(selected[2])

    def speak_article(self):
        self._speak(self.reader.toPlainText())

    def open_audio_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("发音与语速")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("单词发音来源"))
        source = QComboBox()
        source.addItem("词典发音（优先，首次需要联网）", "dictionary")
        source.addItem("系统英文语音", "system")
        source.setCurrentIndex(max(0, source.findData(self.audio_source)))
        layout.addWidget(source)
        layout.addWidget(QLabel("口音"))
        accent = QComboBox()
        accent.addItem("美式发音", "us")
        accent.addItem("英式发音", "uk")
        accent.setCurrentIndex(max(0, accent.findData(self.audio_accent)))
        layout.addWidget(accent)
        layout.addWidget(QLabel("播放速度（单词、句子和全文）"))
        speed = QComboBox()
        for value in (0.6, 0.75, 0.9, 1.0):
            speed.addItem(f"{value:g} 倍速", value)
        speed.setCurrentIndex(max(0, speed.findData(self.audio_speed)))
        layout.addWidget(speed)
        layout.addWidget(QLabel("词典音频会缓存；句段使用系统英文语音。系统语速因语音引擎略有差异。"))
        save = QPushButton("保存")
        save.clicked.connect(dialog.accept)
        layout.addWidget(save)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.stop_audio()
            self.audio_source, self.audio_accent, self.audio_speed = source.currentData(), accent.currentData(), speed.currentData()
            for key, value in (("source", self.audio_source), ("accent", self.audio_accent), ("speed", self.audio_speed)):
                self.audio_settings.setValue(key, value)
            self.audio_settings.sync()
            self.status_label.setText("发音设置已保存。")

    def stop_audio(self):
        self.cancel_sentence_sequence()
        self.audio_request_id += 1
        self._word_generation = -1
        self._audio_text = ""
        self.word_player.stop()
        self.speech.stop()

    def _speak(self, text):
        if not text.strip():
            return
        self.stop_audio()
        try:
            audio_word(text)
            single_word = True
        except PronunciationError:
            single_word = False
        if single_word and self.audio_source == "dictionary":
            self._play_word_audio(text)
        else:
            self._speak_system(text)

    def _play_word_audio(self, text):
        self._audio_text = text
        worker = WordAudioWorker(text, self.audio_accent, self.audio_request_id)
        worker.signals.finished.connect(self._on_word_audio)
        self.thread_pool.start(worker)
        self.status_label.setText("正在载入词典发音……")

    def _on_word_audio(self, request_id, text, result):
        if request_id != self.audio_request_id:
            return
        if isinstance(result, Exception):
            self._speak_system(text)
            self.status_label.setText(str(result))
            return
        self._word_generation = request_id
        self.word_player.setSource(QUrl.fromLocalFile(str(result)))
        self.word_player.setPlaybackRate(self.audio_speed)
        self.word_player.play()
        self.status_label.setText(f"{'美式' if self.audio_accent == 'us' else '英式'}词典发音 · {self.audio_speed:g} 倍速")

    def _word_audio_failed(self, *args):
        if self._audio_text and getattr(self, "_word_generation", -1) == self.audio_request_id:
            self._speak_system(self._audio_text)
            self.status_label.setText("词典音频播放失败，已改用系统英文语音。")

    def _speak_system(self, text):
        locales = self.speech.availableLocales()
        wanted = QLocale("en_GB" if self.audio_accent == "uk" else "en_US")
        fallback = QLocale("en_US")
        self.speech.setLocale(wanted if wanted in locales else fallback)
        self.speech.setRate((self.audio_speed - 1) * 1.2)
        if not self.speech.availableVoices():
            self.cancel_sentence_sequence()
            self._show_hint("未找到英文语音，请在 Windows 语言设置中安装英语语音。")
            return
        self.speech.say(text)
        self.status_label.setText("正在以较慢语速朗读英文，可暂停或停止。")

    def pause_speech(self):
        if hasattr(self,'sentence_timer') and self.sentence_timer.isActive():
            self.sentence_timer.stop(); self._gap_paused = True; self._show_hint('已暂停句间等待'); return
        if getattr(self,'_gap_paused',False):
            self._gap_paused = False; self.sentence_timer.start(0); return
        if self.word_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.word_player.pause()
        elif self.word_player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self.word_player.play()
        elif self.speech.state() == QTextToSpeech.State.Paused:
            self.speech.resume()
        elif self.speech.state() == QTextToSpeech.State.Speaking:
            self.speech.pause()

    def closeEvent(self, event):
        self.save_reading_progress()
        self._loading_article = True
        self.sync_timer.stop()
        self.progress_timer.stop()
        if self.sync_service:
            self.sync_service.stop()
        self.stop_audio()
        self.vocabulary_dialog.close()
        self.lookup_request_id += 1
        super().closeEvent(event)

    def _on_lookup_finished(self, request_id: int, selection: tuple[int, int, str], result: object) -> None:
        if request_id != self.lookup_request_id:
            return
        if isinstance(result, Exception):
            self.current_definition = ""
            self._display_translation(str(result))
            return
        self.current_selection = selection
        self.current_definition = str(result)
        self.definition_selection = selection
        self.selected_word_label.setText(selection[2][:80] + ("…" if len(selection[2]) > 80 else ""))
        self._display_translation(self.current_definition)

    def toggle_underline(self) -> None:
        selected = self._get_selection()
        if selected is None or self.current_article_id is None:
            return
        start, end, word = selected
        annotations = self.repository.list_annotations(self.current_article_id)
        existing = next((item for item in annotations if item["start"] == start and item["end"] == end), None)
        if existing:
            self.repository.remove_annotation(self.current_article_id, start, end)
            fmt = QTextCharFormat()
            fmt.setFontUnderline(False)
            cursor = self.reader.textCursor()
            cursor.mergeCharFormat(fmt)
            self.status_label.setText(f"已取消这处 {word} 的划线。")
        else:
            self.repository.add_annotation(self.current_article_id, start, end, word)
            fmt = QTextCharFormat()
            fmt.setFontUnderline(True)
            fmt.setUnderlineColor(QColor("#d06a35"))
            self.reader.textCursor().mergeCharFormat(fmt)
            self.status_label.setText(f"已标记本文中的这处 {word}。")

    def save_vocabulary(self) -> None:
        selected = self._get_selection()
        if selected is None or self.current_article_id is None:
            return
        definition = self.current_definition if self.definition_selection == selected else ""
        if not definition:
            self._show_hint("先查询该词的中文释义，再加入生词表。")
            return
        self.repository.add_vocabulary(
            self.current_article_id, selected[0], selected[1], selected[2], definition
        )
        self.refresh_vocabulary()
        self.status_label.setText(f"已将 {selected[2]} 加入生词表。")

    def add_pasted_article(self) -> None:
        dialog = ArticleEditorDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._save_article_from_dialog(dialog)

    def add_text_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入文本文章", str(Path.home()), "文本文件 (*.txt);;所有文件 (*)"
        )
        if not file_path:
            return
        path = Path(file_path)
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        dialog = ArticleEditorDialog(path.stem, text, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._save_article_from_dialog(dialog)

    def _save_article_from_dialog(self, dialog: ArticleEditorDialog) -> None:
        title, text = dialog.article()
        if not title or not text:
            self._show_hint("文章标题和正文不能为空。")
            return
        article_id = self.repository.create_article(title, text)
        self.refresh_articles(article_id)

    def export_vocabulary(self) -> None:
        records = self.repository.list_vocabulary()
        if not records:
            self._show_hint("生词表还是空的。")
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出生词表", str(Path.home() / "英语生词表.csv"), "CSV 文件 (*.csv)"
        )
        if not file_path:
            return
        destination = Path(file_path)
        if destination.suffix.lower() != ".csv":
            destination = destination.with_suffix(".csv")
        export_vocabulary_csv(records, destination)
        QMessageBox.information(self, "导出完成", f"生词表已导出到：\n{destination}")

    def open_data_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("数据与备份")
        layout = QVBoxLayout(dialog)
        label = QLabel("文章、划线和生词保存在：\n" + str(self.repository.database_path.parent)
                       + "\n\n每天首次打开自动备份；旧资料库迁移前也会保留副本。")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        open_button = QPushButton("打开数据文件夹")
        open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.repository.database_path.parent))))
        layout.addWidget(open_button)
        backup_button = QPushButton("立即备份")
        def save_backup():
            try:
                path = backup_database(self.repository.database_path)
                QMessageBox.information(dialog, "备份完成", "已保存到：\n" + str(path))
            except Exception as error:
                QMessageBox.warning(dialog, "备份失败", str(error))
        backup_button.clicked.connect(save_backup)
        layout.addWidget(backup_button)
        dialog.resize(580, 230)
        dialog.exec()

    def _show_hint(self, message: str) -> None:
        self.status_label.setText(message)


def _resource_path(relative_path: str) -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    base_path = Path(bundle_root) if bundle_root else Path(__file__).resolve().parent.parent
    return base_path / relative_path


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("EnglishReadingMarker")
    app.setOrganizationName("CodexProjects")
    data_directory().mkdir(parents=True, exist_ok=True)
    app_lock = QLockFile(str(data_directory() / 'application.lock'))
    app_lock.setStaleLockTime(0)
    if not app_lock.tryLock(0):
        QMessageBox.information(None, "程序已打开", "阅读器已经在运行，请使用已打开的窗口。")
        return 0
    try:
        storage = prepare_storage()
        repository = ReaderRepository(storage.database_path)
    except Exception as error:
        QMessageBox.critical(None, "资料读取失败", str(error) + "\n\n程序没有重置资料。请保留原文件和备份。")
        return 1
    window = MainWindow(repository, _resource_path(f"assets/{SAMPLE_NAME}"), seed_sample=storage.first_run)
    window.show()
    exit_code = app.exec()
    repository.close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

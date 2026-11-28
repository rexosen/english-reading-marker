"""Global themes (Paper, Light, Green, Dark), crisp SVG icons, and card list delegates."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

ARTICLE_META_ROLE = Qt.ItemDataRole.UserRole + 10


THEMES: dict[str, dict[str, str]] = {
    "paper": {
        "dark": "0",
        "root_bg": "#f3f1eb",
        "panel_bg": "#ffffff",
        "panel_border": "#e5e0d5",
        "text": "#26231e",
        "title": "#1a1714",
        "muted": "#7a7367",
        "accent": "#2d5bb9",
        "accent_hover": "#224a9c",
        "accent_soft": "#e9f0ff",
        "accent_soft_border": "#c9dafc",
        "btn_bg": "#f6f4ee",
        "btn_border": "#e2ddd2",
        "btn_hover": "#ebe7dd",
        "input_bg": "#ffffff",
        "input_border": "#dcd6c8",
        "list_hover": "#f5f2eb",
        "list_selected_bg": "#e9f0ff",
        "list_selected_fg": "#244fa8",
        "reader_bg": "#fffaf0",
        "reader_fg": "#2c2721",
        "reader_border": "#e6dfd0",
        "selection_bg": "#cfe0ff",
        "underline": "#d06a35",
        "vocab_tint": "#38f5b942",
        "missed_tint": "#33ef4444",
        "sentence_hl": "#66ffcc66",
        "scroll_track": "transparent",
        "scroll_handle": "#d5cfc2",
        "scroll_handle_hover": "#b8b0a0",
        "menu_bg": "#ffffff",
        "menu_border": "#e2ddd2",
        "badge_listening_bg": "#e0f2fe",
        "badge_listening_fg": "#0369a1",
        "badge_reading_bg": "#dcfce7",
        "badge_reading_fg": "#15803d",
        "badge_custom_bg": "#f3e8ff",
        "badge_custom_fg": "#7e22ce",
        "badge_group_bg": "#f1efe9",
        "badge_group_fg": "#5c5549",
    },
    "light": {
        "dark": "0",
        "root_bg": "#f4f6fa",
        "panel_bg": "#ffffff",
        "panel_border": "#e4e9f2",
        "text": "#203044",
        "title": "#142235",
        "muted": "#75849a",
        "accent": "#2f60c2",
        "accent_hover": "#244fa6",
        "accent_soft": "#eaf1ff",
        "accent_soft_border": "#c7d9fc",
        "btn_bg": "#f3f6fb",
        "btn_border": "#e0e6f0",
        "btn_hover": "#e7edf7",
        "input_bg": "#ffffff",
        "input_border": "#dbe2ee",
        "list_hover": "#f2f5fb",
        "list_selected_bg": "#e9f0ff",
        "list_selected_fg": "#2454b5",
        "reader_bg": "#ffffff",
        "reader_fg": "#203044",
        "reader_border": "#e2e8f2",
        "selection_bg": "#cfe0ff",
        "underline": "#d06a35",
        "vocab_tint": "#38f5b942",
        "missed_tint": "#30ef4444",
        "sentence_hl": "#66ffcc66",
        "scroll_track": "transparent",
        "scroll_handle": "#cfd7e3",
        "scroll_handle_hover": "#aebad0",
        "menu_bg": "#ffffff",
        "menu_border": "#dfe6f0",
        "badge_listening_bg": "#e0f2fe",
        "badge_listening_fg": "#0369a1",
        "badge_reading_bg": "#dcfce7",
        "badge_reading_fg": "#15803d",
        "badge_custom_bg": "#f3e8ff",
        "badge_custom_fg": "#7e22ce",
        "badge_group_bg": "#eef2f8",
        "badge_group_fg": "#4e607a",
    },
    "green": {
        "dark": "0",
        "root_bg": "#eaf1e6",
        "panel_bg": "#f7fbf5",
        "panel_border": "#d6e4d0",
        "text": "#223627",
        "title": "#17291c",
        "muted": "#617967",
        "accent": "#2b6f4b",
        "accent_hover": "#215a3c",
        "accent_soft": "#dff0e5",
        "accent_soft_border": "#b8dec6",
        "btn_bg": "#eef5eb",
        "btn_border": "#d4e3ce",
        "btn_hover": "#e1ecdc",
        "input_bg": "#ffffff",
        "input_border": "#cfe0c8",
        "list_hover": "#edf5ea",
        "list_selected_bg": "#dcf0e3",
        "list_selected_fg": "#1e5c3b",
        "reader_bg": "#e8f2e2",
        "reader_fg": "#223627",
        "reader_border": "#cfe0c8",
        "selection_bg": "#b9dfc6",
        "underline": "#c25e2e",
        "vocab_tint": "#40eab308",
        "missed_tint": "#33ef4444",
        "sentence_hl": "#66fde047",
        "scroll_track": "transparent",
        "scroll_handle": "#bdd1b6",
        "scroll_handle_hover": "#9eb896",
        "menu_bg": "#f9fcf8",
        "menu_border": "#d4e3ce",
        "badge_listening_bg": "#dbeafe",
        "badge_listening_fg": "#1d4ed8",
        "badge_reading_bg": "#d1fae5",
        "badge_reading_fg": "#047857",
        "badge_custom_bg": "#ede9fe",
        "badge_custom_fg": "#6d28d9",
        "badge_group_bg": "#e3efe0",
        "badge_group_fg": "#47634d",
    },
    "dark": {
        "dark": "1",
        "root_bg": "#121720",
        "panel_bg": "#1a212d",
        "panel_border": "#2a3444",
        "text": "#dde6f2",
        "title": "#f1f5f9",
        "muted": "#8c9bb0",
        "accent": "#4c8dff",
        "accent_hover": "#3b7cef",
        "accent_soft": "#1f3252",
        "accent_soft_border": "#33548a",
        "btn_bg": "#232c3b",
        "btn_border": "#323f54",
        "btn_hover": "#2c3749",
        "input_bg": "#151b25",
        "input_border": "#323f54",
        "list_hover": "#232c3b",
        "list_selected_bg": "#213659",
        "list_selected_fg": "#82b4ff",
        "reader_bg": "#1b222e",
        "reader_fg": "#dde6f2",
        "reader_border": "#2d3849",
        "selection_bg": "#2b4d80",
        "underline": "#f59e56",
        "vocab_tint": "#33f59e0b",
        "missed_tint": "#44ef4444",
        "sentence_hl": "#48facc15",
        "scroll_track": "transparent",
        "scroll_handle": "#39465c",
        "scroll_handle_hover": "#4e5f7c",
        "menu_bg": "#1f2735",
        "menu_border": "#323f54",
        "badge_listening_bg": "#17344f",
        "badge_listening_fg": "#60b8ff",
        "badge_reading_bg": "#163b2a",
        "badge_reading_fg": "#5ce09e",
        "badge_custom_bg": "#32224d",
        "badge_custom_fg": "#c49bff",
        "badge_group_bg": "#253042",
        "badge_group_fg": "#a7b5c9",
    },
}


def get_theme(name: str) -> dict[str, str]:
    return THEMES.get(name, THEMES["paper"])


def is_dark_theme(name: str) -> bool:
    return get_theme(name)["dark"] == "1"


def build_stylesheet(theme_name: str) -> str:
    t = get_theme(theme_name)
    return f"""
    QWidget {{
        color: {t['text']};
        font-family: "Microsoft YaHei UI";
        font-size: 10pt;
    }}
    QMainWindow, QDialog, QWidget#root {{
        background: {t['root_bg']};
    }}
    QMenuBar {{
        background: {t['root_bg']};
        color: {t['muted']};
        border: 0;
        padding: 2px 10px;
        font-size: 9.5pt;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 4px 10px;
        border-radius: 6px;
    }}
    QMenuBar::item:selected {{
        background: {t['btn_hover']};
        color: {t['text']};
    }}
    QMenu {{
        background: {t['menu_bg']};
        border: 1px solid {t['menu_border']};
        border-radius: 10px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 22px 7px 14px;
        border-radius: 6px;
        color: {t['text']};
    }}
    QMenu::item:selected {{
        background: {t['list_selected_bg']};
        color: {t['list_selected_fg']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {t['panel_border']};
        margin: 4px 8px;
    }}
    QLabel#brand {{
        color: {t['muted']};
        font-size: 9pt;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QLabel#pageTitle {{
        color: {t['title']};
        font-size: 16pt;
        font-weight: 700;
    }}
    QLabel#sectionTitle {{
        color: {t['title']};
        font-size: 12pt;
        font-weight: 700;
    }}
    QLabel#muted {{
        color: {t['muted']};
        font-size: 9.5pt;
    }}
    QLabel#definition {{
        color: {t['accent']};
        font-size: 14pt;
        font-weight: 700;
    }}
    QFrame#panel {{
        background: {t['panel_bg']};
        border: 1px solid {t['panel_border']};
        border-radius: 14px;
    }}
    QFrame#popupPanel {{
        background: {t['panel_bg']};
        border: 1px solid {t['panel_border']};
        border-radius: 14px;
    }}
    QFrame#statCard {{
        background: {t['panel_bg']};
        border: 1px solid {t['panel_border']};
        border-radius: 12px;
        padding: 12px;
    }}
    QSplitter::handle {{
        background: transparent;
        width: 8px;
    }}
    QSplitter::handle:hover {{
        background: {t['accent_soft']};
        border-radius: 4px;
    }}
    QListWidget {{
        background: transparent;
        border: 0;
        outline: 0;
        padding: 2px;
    }}
    QListWidget::item {{
        padding: 10px 10px;
        border-radius: 9px;
        margin: 2px 0;
        color: {t['text']};
    }}
    QListWidget::item:selected {{
        background: {t['list_selected_bg']};
        color: {t['list_selected_fg']};
    }}
    QListWidget::item:hover {{
        background: {t['list_hover']};
    }}
    QTextEdit, QTextBrowser {{
        background: {t['input_bg']};
        color: {t['text']};
        border: 1px solid {t['input_border']};
        border-radius: 10px;
        padding: 12px;
        selection-background-color: {t['selection_bg']};
    }}
    QPushButton, QToolButton {{
        background: {t['btn_bg']};
        color: {t['text']};
        border: 1px solid {t['btn_border']};
        border-radius: 9px;
        padding: 7px 12px;
    }}
    QPushButton:hover, QToolButton:hover {{
        background: {t['btn_hover']};
    }}
    QPushButton:checked, QToolButton:checked {{
        background: {t['accent_soft']};
        color: {t['list_selected_fg']};
        border: 1px solid {t['accent_soft_border']};
        font-weight: 700;
    }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {t['muted']};
        opacity: 0.6;
    }}
    QPushButton#primaryButton, QToolButton#primaryButton {{
        background: {t['accent']};
        color: #ffffff;
        border: 0;
        font-weight: 700;
    }}
    QPushButton#primaryButton:hover, QToolButton#primaryButton:hover {{
        background: {t['accent_hover']};
    }}
    QToolButton#speedButton {{
        background: {t['accent_soft']};
        color: {t['list_selected_fg']};
        border: 1px solid {t['accent_soft_border']};
        border-radius: 10px;
        font-weight: 700;
        padding: 8px 14px;
    }}
    QToolButton#speedButton:hover {{
        background: {t['list_selected_bg']};
    }}
    QToolButton::menu-indicator {{
        width: 10px;
        subcontrol-position: right center;
        subcontrol-origin: padding;
        right: 4px;
    }}
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        padding: 7px 10px;
        border: 1px solid {t['input_border']};
        border-radius: 8px;
        background: {t['input_bg']};
        color: {t['text']};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {t['accent']};
    }}
    QComboBox::drop-down {{
        border: 0;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {t['menu_bg']};
        color: {t['text']};
        border: 1px solid {t['menu_border']};
        selection-background-color: {t['list_selected_bg']};
        selection-color: {t['list_selected_fg']};
        outline: 0;
    }}
    QCheckBox {{
        spacing: 6px;
        color: {t['text']};
    }}
    QProgressBar {{
        background: {t['btn_bg']};
        border: 0;
        border-radius: 3px;
        max-height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {t['accent']};
        border-radius: 3px;
    }}
    QScrollBar:vertical {{
        background: {t['scroll_track']};
        width: 8px;
        margin: 4px 2px 4px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {t['scroll_handle']};
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {t['scroll_handle_hover']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: {t['scroll_track']};
        height: 8px;
        margin: 0 4px 2px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {t['scroll_handle']};
        border-radius: 4px;
        min-width: 28px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: none;
        width: 0;
    }}
    """


# ---- Crisp inline monochrome SVG icons --------------------------------------

_SVG_PATHS: dict[str, str] = {
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "import": '<path d="M12 3v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    "sync": '<path d="M21 12a9 9 0 0 1-15.5 6.3M3 12a9 9 0 0 1 15.5-6.3"/><path d="M21 3v6h-6M3 21v-6h6"/>',
    "stats": '<path d="M4 20V10m6 10V4m6 16v-7m4 7H2"/>',
    "translate": '<path d="M5 8l6 6M4 14l6-6 2-3M2 5h12M7 2h1m4 18l5-10 5 10m-1.4-3h-7.2"/>',
    "underline": '<path d="M6 4v6a6 6 0 0 0 12 0V4M4 20h16"/>',
    "play": '<polygon points="6 4 20 12 6 20 6 4"/>',
    "focus": '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "study": '<path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
}


def make_svg_icon(name: str, color: str = "#203044", size: int = 16) -> QIcon:
    body = _SVG_PATHS.get(name, "")
    if not body:
        return QIcon()
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )
    pix = QPixmap()
    pix.loadFromData(QByteArray(svg.encode("utf-8")), "SVG")
    return QIcon(pix)


# ---- Custom two-line card delegates -----------------------------------------

class ArticleCardDelegate(QStyledItemDelegate):
    """Paints a two-line article card while keeping item.text() untouched for tests."""

    def __init__(self, parent=None, theme_name: str = "paper") -> None:
        super().__init__(parent)
        self.theme_name = theme_name

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), 56)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        t = get_theme(self.theme_name)
        meta = index.data(ARTICLE_META_ROLE) or {}
        title = meta.get("title") or index.data(Qt.ItemDataRole.DisplayRole) or ""
        pinned = bool(meta.get("pinned"))
        read = bool(meta.get("read"))
        group_name = meta.get("group_name") or ""
        word_count = int(meta.get("word_count") or 0)
        progress = int(meta.get("progress") or 0)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(2, 2, -2, -2)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setBrush(QColor(t["list_selected_bg"]))
            painter.setPen(QPen(QColor(t["accent_soft_border"]), 1))
            painter.drawRoundedRect(rect, 9, 9)
        elif hovered:
            painter.setBrush(QColor(t["list_hover"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 9, 9)

        inner = rect.adjusted(10, 7, -10, -7)
        title_font = QFont(option.font)
        title_font.setPointSize(10)
        title_font.setBold(selected or pinned)
        painter.setFont(title_font)

        prefix = "★ " if pinned else ""
        suffix = " ✓" if read else ""
        display_title = f"{prefix}{title}{suffix}"
        fm_title = QFontMetrics(title_font)
        elided_title = fm_title.elidedText(display_title, Qt.TextElideMode.ElideRight, inner.width())
        painter.setPen(QColor(t["list_selected_fg"] if selected else t["title"]))
        painter.drawText(
            QRect(inner.left(), inner.top(), inner.width(), 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided_title,
        )

        # Second line: group pill + word count + progress
        sub_font = QFont(option.font)
        sub_font.setPointSize(8)
        painter.setFont(sub_font)
        fm_sub = QFontMetrics(sub_font)
        x = inner.left()
        y = inner.top() + 23
        if group_name:
            pill_w = min(fm_sub.horizontalAdvance(group_name) + 12, inner.width() // 2)
            pill_rect = QRect(x, y, pill_w, 17)
            painter.setBrush(QColor(t["badge_group_bg"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(pill_rect, 4, 4)
            painter.setPen(QColor(t["badge_group_fg"]))
            painter.drawText(
                pill_rect.adjusted(5, 0, -5, 0),
                Qt.AlignmentFlag.AlignCenter,
                fm_sub.elidedText(group_name, Qt.TextElideMode.ElideRight, pill_w - 8),
            )
            x += pill_w + 6

        bits = []
        if word_count:
            bits.append(f"{word_count} 词")
        if progress > 0:
            bits.append(f"{progress}%")
        sub_text = " · ".join(bits) if bits else "未开始"
        painter.setPen(QColor(t["muted"]))
        painter.drawText(
            QRect(x, y, max(0, inner.right() - x), 17),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fm_sub.elidedText(sub_text, Qt.TextElideMode.ElideRight, max(0, inner.right() - x)),
        )
        painter.restore()


class VocabularyCardDelegate(QStyledItemDelegate):
    """Paints a two-line vocabulary card with a colored category pill while keeping item.text() intact."""

    def __init__(self, parent=None, theme_name: str = "paper") -> None:
        super().__init__(parent)
        self.theme_name = theme_name

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), 58)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        t = get_theme(self.theme_name)
        record = index.data(Qt.ItemDataRole.UserRole) or {}
        if not isinstance(record, dict):
            super().paint(painter, option, index)
            return
        word = record.get("word", "")
        definition = (record.get("definition") or "暂无释义").replace("\n", "；")
        cat_key = record.get("category") or ""
        cat_name = record.get("category_name") or ""
        manual = bool(record.get("manual"))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(2, 2, -2, -2)

        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setBrush(QColor(t["list_selected_bg"]))
            painter.setPen(QPen(QColor(t["accent_soft_border"]), 1))
            painter.drawRoundedRect(rect, 9, 9)
        elif hovered:
            painter.setBrush(QColor(t["list_hover"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 9, 9)

        inner = rect.adjusted(12, 7, -12, -7)

        # Category badge on the top right
        badge_w = 0
        if cat_name:
            badge_font = QFont(option.font)
            badge_font.setPointSize(8)
            badge_font.setBold(True)
            fm_badge = QFontMetrics(badge_font)
            badge_w = min(fm_badge.horizontalAdvance(cat_name) + 14, 110)
            badge_rect = QRect(inner.right() - badge_w, inner.top() + 1, badge_w, 19)
            if cat_key == "vgroup:auto:listening":
                bg, fg = t["badge_listening_bg"], t["badge_listening_fg"]
            elif cat_key == "vgroup:auto:reading":
                bg, fg = t["badge_reading_bg"], t["badge_reading_fg"]
            else:
                bg, fg = t["badge_custom_bg"], t["badge_custom_fg"]
            painter.setBrush(QColor(bg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, 5, 5)
            painter.setFont(badge_font)
            painter.setPen(QColor(fg))
            painter.drawText(
                badge_rect,
                Qt.AlignmentFlag.AlignCenter,
                fm_badge.elidedText(cat_name, Qt.TextElideMode.ElideRight, badge_w - 8),
            )
            badge_w += 8

        # Word on top left
        word_font = QFont(option.font)
        word_font.setPointSize(11)
        word_font.setBold(True)
        painter.setFont(word_font)
        fm_word = QFontMetrics(word_font)
        prefix = "✎ " if manual else ""
        word_rect = QRect(inner.left(), inner.top(), max(40, inner.width() - badge_w), 22)
        painter.setPen(QColor(t["list_selected_fg"] if selected else t["title"]))
        painter.drawText(
            word_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fm_word.elidedText(prefix + word, Qt.TextElideMode.ElideRight, word_rect.width()),
        )

        # Definition preview on second line
        def_font = QFont(option.font)
        def_font.setPointSize(9)
        painter.setFont(def_font)
        fm_def = QFontMetrics(def_font)
        def_rect = QRect(inner.left(), inner.top() + 24, inner.width(), 19)
        painter.setPen(QColor(t["muted"]))
        painter.drawText(
            def_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fm_def.elidedText(definition, Qt.TextElideMode.ElideRight, def_rect.width()),
        )
        painter.restore()

"""
实时动态推送面板 — 事件流与桌面通知
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QListWidget,
                              QListWidgetItem, QMenu, QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QDesktopServices, QAction, QColor, QCursor

from src.common.protocol import TYPE_NEW_EVENT
from src.common.logger import get_logger

log = get_logger("stream_panel")

# 事件类型图标
EVENT_ICONS = {
    "PushEvent": "📝", "CreateEvent": "📂", "ReleaseEvent": "🚀",
    "IssuesEvent": "🐛", "IssueCommentEvent": "💬",
    "PullRequestEvent": "🔀", "PullRequestReviewEvent": "👀",
    "WatchEvent": "⭐", "ForkEvent": "🍴", "DeleteEvent": "🗑",
    "PublicEvent": "🌍", "MemberEvent": "👤",
    "Unknown": "❓",
}

# 重要性配色
IMPORTANCE_COLORS = {
    "high": ("#FFD700", "#3A3000"),    # 金色背景
    "medium": ("#4EC9B0", "#002B20"),  # 青色背景
    "low": ("#DCDCDC", "#1E2A1E"),     # 淡色背景
}

HIGHLIGHT_DURATION = 3000  # 3秒高亮


class StreamPanel(QWidget):
    """实时消息流面板"""

    unread_count_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._unread_count = 0
        self._event_count = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题栏
        header = QHBoxLayout()
        title = QLabel("📡 实时动态")
        title.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        self.count_label = QLabel("0 条事件")
        self.count_label.setStyleSheet("color: #888;")
        header.addWidget(self.count_label)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setFixedWidth(60)
        self.clear_btn.clicked.connect(self._clear_events)
        header.addWidget(self.clear_btn)

        layout.addLayout(header)

        # 消息列表
        self.event_list = QListWidget()
        self.event_list.setAlternatingRowColors(True)
        self.event_list.setWordWrap(True)
        self.event_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.event_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.event_list, 1)

        # 连接状态
        self.connection_label = QLabel("⚪ 未连接")
        self.connection_label.setStyleSheet("color: #888; padding: 2px;")
        layout.addWidget(self.connection_label)

    # ─── 事件添加 ────────────────────────────

    def add_event(self, event: dict, monitor_target: str = ""):
        """添加一条事件到流"""
        self._event_count += 1
        self._unread_count += 1
        self.count_label.setText(f"{self._event_count} 条事件")
        self.unread_count_changed.emit(self._unread_count)

        etype = event.get("type", "Unknown")
        actor = event.get("actor", "")
        repo_name = event.get("repo_name", "")
        summary = event.get("summary", "")
        importance = event.get("importance", "low")
        url = event.get("url", "")

        icon = EVENT_ICONS.get(etype, "❓")
        fg_color, bg_color = IMPORTANCE_COLORS.get(importance, ("#DCDCDC", "#1E1E1E"))

        text = f"  {icon} [{etype}]"
        if repo_name:
            text += f"\n      📦 {repo_name}"
        if actor:
            text += f"  👤 {actor}"
        if summary:
            text += f"\n      {summary}"
        if monitor_target:
            text += f"\n      🔔 {monitor_target}"

        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, {
            "url": url, "event": event, "monitor_target": monitor_target
        })
        item.setForeground(QColor(fg_color))

        # 插入到最前面 (新的在上面)
        self.event_list.insertItem(0, item)

        # 3秒高亮
        self._highlight_item(item, bg_color)

    def _highlight_item(self, item: QListWidgetItem, bg_hex: str):
        """设置高亮后渐消"""
        bg = QColor(bg_hex)
        item.setBackground(bg)

        # 3秒后恢复
        QTimer.singleShot(HIGHLIGHT_DURATION, lambda: self._unhighlight(item))

    def _unhighlight(self, item: QListWidgetItem):
        """恢复默认背景"""
        # 设置回默认交替色
        item.setBackground(QColor(Qt.GlobalColor.transparent))

    # ─── 连接状态 ────────────────────────────

    def set_connected(self, connected: bool):
        if connected:
            self.connection_label.setText("🟢 已连接")
            self.connection_label.setStyleSheet("color: #4EC9B0; padding: 2px;")
        else:
            self.connection_label.setText("🔴 已断开 · 重连中...")
            self.connection_label.setStyleSheet("color: #FF4444; padding: 2px;")

    # ─── 操作 ────────────────────────────────

    def _clear_events(self):
        self.event_list.clear()
        self._event_count = 0
        self._unread_count = 0
        self.count_label.setText("0 条事件")
        self.unread_count_changed.emit(0)

    def mark_all_read(self):
        self._unread_count = 0
        self.unread_count_changed.emit(0)

    def _show_context_menu(self, pos):
        item = self.event_list.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        url = data.get("url", "")

        menu = QMenu(self)
        if url:
            open_link = QAction("🌐 在浏览器中打开", self)
            open_link.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
            menu.addAction(open_link)

        copy = QAction("📋 复制事件文本", self)
        copy.triggered.connect(lambda: self._copy_event_text(item.text()))
        menu.addAction(copy)

        menu.addSeparator()

        mark_read = QAction("✅ 标记为已读", self)
        mark_read.triggered.connect(self.mark_all_read)
        menu.addAction(mark_read)

        menu.exec(QCursor.pos())

    def _copy_event_text(self, text: str):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text.strip())

"""
搜索面板 — 全局搜索栏 + 精选结果列表
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLineEdit, QPushButton, QComboBox,
                              QListWidget, QListWidgetItem, QLabel,
                              QSpinBox, QCheckBox, QMenu, QMessageBox,
                              QSplitter)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QAction, QCursor

from src.common.config import config
from src.common.protocol import (TYPE_SEARCH_RESULT, TYPE_ACK,
                                  ACTION_SEARCH_REPOS)
from src.common.logger import get_logger

log = get_logger("search_panel")

LANGUAGES = ["", "Python", "Java", "Go", "JavaScript", "TypeScript",
             "Rust", "C", "C++", "Ruby", "PHP", "Swift", "Kotlin",
             "Scala", "Dart", "Elixir", "Haskell", "Lua", "Shell"]


class SearchPanel(QWidget):
    """全局搜索面板"""

    add_monitor_requested = pyqtSignal(str, str)  # repo_full_name, type
    bookmark_requested = pyqtSignal(str, str, str, str, int)  # name, url, desc, lang, stars
    open_url_requested = pyqtSignal(str)  # url

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self._search_results = []
        self._history = []
        self._search_timeout = None

        # 连接信号
        self.client.message_received.connect(self._on_message)
        self.client.status_changed.connect(self._on_status)

        self._setup_ui()
        self._load_history()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 搜索栏区域 ──
        search_layout = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索 GitHub 项目 (in:name)...")
        self.search_input.setFont(QFont("Consolas", 11))
        self.search_input.setMinimumHeight(34)
        self.search_input.returnPressed.connect(self._do_search)
        search_layout.addWidget(self.search_input, 1)

        self.search_btn = QPushButton("搜索")
        self.search_btn.setMinimumHeight(34)
        self.search_btn.clicked.connect(self._do_search)
        search_layout.addWidget(self.search_btn)

        layout.addLayout(search_layout)

        # ── 筛选器区域 ──
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES)
        self.lang_combo.setMinimumWidth(120)
        filter_layout.addWidget(self.lang_combo)

        filter_layout.addWidget(QLabel("Stars ≥"))
        self.stars_min = QSpinBox()
        self.stars_min.setRange(0, 1000000)
        self.stars_min.setValue(0)
        self.stars_min.setSingleStep(100)
        self.stars_min.setMinimumWidth(90)
        filter_layout.addWidget(self.stars_min)

        filter_layout.addWidget(QLabel("≤"))
        self.stars_max = QSpinBox()
        self.stars_max.setRange(0, 1000000)
        self.stars_max.setValue(0)
        self.stars_max.setSpecialValueText("不限")
        self.stars_max.setMinimumWidth(90)
        filter_layout.addWidget(self.stars_max)

        filter_layout.addStretch()

        layout.addLayout(filter_layout)

        # ── 结果列表 ──
        self.result_list = QListWidget()
        self.result_list.setAlternatingRowColors(True)
        self.result_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.result_list.customContextMenuRequested.connect(self._show_context_menu)
        self.result_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.result_list, 1)

        # ── 状态栏 ──
        status_layout = QHBoxLayout()
        self.rate_label = QLabel("API: --")
        self.rate_label.setStyleSheet("color: #888;")
        status_layout.addWidget(self.rate_label)
        status_layout.addStretch()
        self.result_count_label = QLabel("")
        self.result_count_label.setStyleSheet("color: #888;")
        status_layout.addWidget(self.result_count_label)
        layout.addLayout(status_layout)

    # ─── 搜索逻辑 ────────────────────────────

    def _do_search(self):
        query = self.search_input.text().strip()
        if not query:
            return

        language = self.lang_combo.currentText()
        stars_min = self.stars_min.value()
        stars_max = self.stars_max.value()

        self.search_input.setEnabled(False)
        self.search_btn.setEnabled(False)
        self.search_btn.setText("搜索中...")

        # 15秒超时保护
        if self._search_timeout:
            self._search_timeout.stop()
        self._search_timeout = QTimer(self)
        self._search_timeout.setSingleShot(True)
        self._search_timeout.timeout.connect(self._reset_search_state)
        self._search_timeout.start(15_000)

        self.client.send_command(
            ACTION_SEARCH_REPOS,
            query=query, language=language,
            stars_min=stars_min, stars_max=stars_max,
        )

    def _reset_search_state(self):
        """恢复搜索按钮状态 (超时或错误时)"""
        self.search_input.setEnabled(True)
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")
        if self._search_timeout:
            self._search_timeout.stop()
            self._search_timeout = None

    def _on_status(self, code: str, message: str):
        """处理状态消息, 恢复搜索状态"""
        if "search" in message.lower():
            self._reset_search_state()

    def _on_message(self, msg_type: str, data: dict):
        if msg_type == TYPE_SEARCH_RESULT:
            self._handle_search_result(data)
        elif msg_type == TYPE_ACK and data.get("action") == "search_history":
            self._handle_history(data)

    def _handle_search_result(self, data: dict):
        self.search_input.setEnabled(True)
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")

        items = data.get("data", [])
        remaining = data.get("rate_remaining", 0)

        self._search_results = items
        self.result_list.clear()
        self.result_count_label.setText(f"共 {len(items)} 条结果")
        self.rate_label.setText(f"API 剩余: {remaining}")

        self._update_rate_style(remaining)

        if not items:
            item = QListWidgetItem("  未找到匹配的项目，请尝试其他关键词或放宽筛选条件")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.result_list.addItem(item)
            return

        for repo in items:
            self.result_list.addItem(self._build_repo_item(repo))

    def _build_repo_item(self, repo: dict) -> QListWidgetItem:
        """构建仓库列表项的显示文本"""
        name = repo.get("full_name", "")
        desc = repo.get("description", "")
        lang = repo.get("language", "") or "-"
        stars = repo.get("stars", 0)
        forks = repo.get("forks", 0)
        updated = repo.get("updated_at", "")[:10]

        text = f"  {name}"
        if desc:
            text += f"\n  {desc[:100]}"
        text += f"\n  🔠 {lang}  ⭐ {stars:,}  🍴 {forks:,}  🕐 {updated}"

        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, repo)
        return item

    def _update_rate_style(self, remaining: int):
        if remaining < 10:
            self.rate_label.setStyleSheet("color: #FF4444; font-weight: bold;")
        elif remaining < 50:
            self.rate_label.setStyleSheet("color: #FF8800;")
        else:
            self.rate_label.setStyleSheet("color: #888;")

    # ─── 右键菜单 ────────────────────────────

    def _show_context_menu(self, pos):
        item = self.result_list.itemAt(pos)
        if not item:
            return
        repo = item.data(Qt.ItemDataRole.UserRole)
        if not repo:
            return

        menu = QMenu(self)

        add_monitor = QAction("🔔 添加到监控", self)
        add_monitor.triggered.connect(
            lambda: self.add_monitor_requested.emit(repo["full_name"], "repo"))
        menu.addAction(add_monitor)

        bookmark = QAction("⭐ 收藏到本地", self)
        bookmark.triggered.connect(
            lambda: self.bookmark_requested.emit(
                repo["full_name"], repo.get("url", ""),
                repo.get("description", ""), repo.get("language", ""),
                repo.get("stars", 0)))
        menu.addAction(bookmark)

        menu.addSeparator()

        open_repo = QAction("🌐 在浏览器中打开", self)
        open_repo.triggered.connect(
            lambda: self.open_url_requested.emit(repo.get("url", "")))
        menu.addAction(open_repo)

        menu.exec(QCursor.pos())

    def _on_item_double_clicked(self, item):
        repo = item.data(Qt.ItemDataRole.UserRole)
        if repo:
            self.open_url_requested.emit(repo.get("url", ""))

    # ─── 历史管理 ────────────────────────────

    def _load_history(self):
        self.client.send_command("search_history")

    def _handle_history(self, data: dict):
        self._history = data.get("history", [])

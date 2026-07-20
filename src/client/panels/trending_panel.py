"""
趋势榜单面板 — 实时显示 GitHub Trending
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QComboBox, QPushButton, QListWidget,
                              QListWidgetItem, QLabel, QMenu, QCheckBox)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QAction, QColor, QCursor

from src.common.config import config
from src.common.protocol import (TYPE_TRENDING_DATA, TYPE_ACK,
                                  ACTION_FETCH_TRENDING)
from src.common.logger import get_logger

log = get_logger("trending_panel")

LANGUAGES = ["All", "Python", "Java", "Go", "JavaScript", "TypeScript",
             "Rust", "C", "C++", "Ruby", "PHP", "Swift", "Kotlin",
             "Scala", "Dart", "Elixir", "Haskell", "Lua"]

LANG_COLORS = {
    "Python": "#3572A5", "Java": "#B07219", "Go": "#00ADD8",
    "JavaScript": "#F7DF1E", "TypeScript": "#3178C6", "Rust": "#DEA584",
    "C": "#555555", "C++": "#F34B7D", "Ruby": "#701516",
    "PHP": "#4F5D95", "Swift": "#FFAC45", "Kotlin": "#F18E33",
    "Scala": "#C22D40", "Dart": "#00B4AB", "Elixir": "#6E4A7E",
    "Haskell": "#5D4F85", "Lua": "#000080",
}


class TrendingPanel(QWidget):
    """趋势榜单面板"""

    add_monitor_requested = pyqtSignal(str, str)
    bookmark_requested = pyqtSignal(str, str, str, str, int)
    open_url_requested = pyqtSignal(str)
    view_insight_requested = pyqtSignal(str)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self._current_data = []
        self._auto_refresh_enabled = True
        self._refresh_timeout = None  # 超时定时器

        self.client.message_received.connect(self._on_message)
        self.client.status_changed.connect(self._on_status)
        self._setup_ui()
        self._start_auto_refresh()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title = QLabel("📈 GitHub 趋势")
        title.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # 控制栏
        controls = QHBoxLayout()

        controls.addWidget(QLabel("语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(LANGUAGES)
        self.lang_combo.currentTextChanged.connect(self._refresh)
        controls.addWidget(self.lang_combo)

        controls.addWidget(QLabel("周期:"))
        self.since_combo = QComboBox()
        self.since_combo.addItems(["今日", "本周", "本月"])
        self.since_combo.setItemData(0, "daily")
        self.since_combo.setItemData(1, "weekly")
        self.since_combo.setItemData(2, "monthly")
        self.since_combo.currentIndexChanged.connect(self._refresh)
        controls.addWidget(self.since_combo)

        controls.addStretch()

        self.auto_refresh_cb = QCheckBox("自动刷新")
        self.auto_refresh_cb.setChecked(True)
        self.auto_refresh_cb.toggled.connect(self._toggle_auto_refresh)
        controls.addWidget(self.auto_refresh_cb)

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self._refresh)
        controls.addWidget(self.refresh_btn)

        layout.addLayout(controls)

        # 列表
        self.repo_list = QListWidget()
        self.repo_list.setAlternatingRowColors(True)
        self.repo_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.repo_list.customContextMenuRequested.connect(self._show_context_menu)
        self.repo_list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.repo_list, 1)

    # ─── 数据刷新 ────────────────────────────

    def _refresh(self):
        lang = self.lang_combo.currentText().lower() if self.lang_combo.currentText() != "All" else "all"
        since = self.since_combo.currentData() or "daily"

        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("获取中...")

        # 15秒超时保护: 如果服务端没响应, 自动恢复按钮状态
        if self._refresh_timeout:
            self._refresh_timeout.stop()
        self._refresh_timeout = QTimer(self)
        self._refresh_timeout.setSingleShot(True)
        self._refresh_timeout.timeout.connect(self._reset_refresh_state)
        self._refresh_timeout.start(15_000)

        self.client.send_command(ACTION_FETCH_TRENDING, language=lang, since=since)

    def _reset_refresh_state(self):
        """恢复刷新按钮状态 (超时或错误时调用)"""
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 刷新")
        if self._refresh_timeout:
            self._refresh_timeout.stop()
            self._refresh_timeout = None
        log.warning("Trending 刷新超时, 请检查连接")

    def _on_message(self, msg_type: str, data: dict):
        if msg_type == TYPE_TRENDING_DATA:
            self._handle_data(data)
        elif msg_type == TYPE_ACK and data.get("action") == "fetch_trending" and not data.get("success"):
            self._reset_refresh_state()
            log.warning("Trending 获取失败: %s", data.get("error", ""))

    def _on_status(self, code: str, message: str):
        """处理服务端推送的状态消息"""
        if "trending" in message.lower() or "trend" in message.lower():
            self._reset_refresh_state()
        # 在列表底部显示状态
        if code in ("error", "rate_limit"):
            placeholder = self.repo_list.findItems("", Qt.MatchFlag.MatchContains)
            if not placeholder or not self.repo_list.count():
                item = QListWidgetItem(f"  ⚠ {message}")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.repo_list.addItem(item)

    def _handle_data(self, data: dict):
        # 取消超时定时器
        if self._refresh_timeout:
            self._refresh_timeout.stop()
            self._refresh_timeout = None
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 刷新")

        repos = data.get("data", [])
        self._current_data = repos
        self.repo_list.clear()

        if not repos:
            item = QListWidgetItem("  暂无趋势数据，请检查网络或稍后重试")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.repo_list.addItem(item)
            return

        for i, repo in enumerate(repos, 1):
            text = self._format_repo_line(i, repo)
            list_item = QListWidgetItem(text)
            list_item.setData(Qt.ItemDataRole.UserRole, repo)
            self.repo_list.addItem(list_item)

    def _format_repo_line(self, index: int, repo: dict) -> str:
        name = repo.get("full_name", repo.get("name", ""))
        desc = repo.get("description", "")
        lang = repo.get("language", "")
        stars = repo.get("stars", 0)
        forks = repo.get("forks", 0)
        daily = repo.get("daily_stars", 0)

        lines = [f"  #{index:2d}  {name}"]
        if desc:
            lines.append(f"       {desc[:90]}")
        daily_str = f" 📈 +{daily:,}" if daily else ""
        lines.append(f"       ⭐ {stars:,}  🍴 {forks:,}{daily_str}  🔠 {lang or '-'}")
        return "\n".join(lines)

    # ─── 自动刷新 ────────────────────────────

    def _start_auto_refresh(self):
        interval = config.get("trending_refresh_seconds", 600)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(interval * 1000)

    def _toggle_auto_refresh(self, enabled: bool):
        if hasattr(self, '_timer'):
            if enabled:
                self._timer.start()
            else:
                self._timer.stop()

    # ─── 右键菜单 ────────────────────────────

    def _show_context_menu(self, pos):
        item = self.repo_list.itemAt(pos)
        if not item:
            return
        repo = item.data(Qt.ItemDataRole.UserRole)
        if not repo:
            return

        menu = QMenu(self)

        add_mon = QAction("🔔 添加到监控", self)
        add_mon.triggered.connect(
            lambda: self.add_monitor_requested.emit(repo.get("full_name", ""), "repo"))
        menu.addAction(add_mon)

        bookmark = QAction("⭐ 收藏", self)
        bookmark.triggered.connect(
            lambda: self.bookmark_requested.emit(
                repo.get("full_name", ""), repo.get("url", ""),
                repo.get("description", ""), repo.get("language", ""),
                repo.get("stars", 0)))
        menu.addAction(bookmark)

        insight = QAction("📊 查看洞察", self)
        insight.triggered.connect(
            lambda: self.view_insight_requested.emit(repo.get("full_name", "")))
        menu.addAction(insight)

        menu.addSeparator()

        open_repo = QAction("🌐 在浏览器中打开", self)
        open_repo.triggered.connect(
            lambda: self.open_url_requested.emit(
                repo.get("url", f"https://github.com/{repo.get('full_name', '')}")))
        menu.addAction(open_repo)

        menu.exec(QCursor.pos())

    def _on_double_click(self, item):
        repo = item.data(Qt.ItemDataRole.UserRole)
        if repo:
            url = repo.get("url", f"https://github.com/{repo.get('full_name', '')}")
            self.open_url_requested.emit(url)

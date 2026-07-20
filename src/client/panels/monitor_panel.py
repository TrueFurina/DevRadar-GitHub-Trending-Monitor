"""
监控管理面板 — 添加/删除监控目标, 配置过滤规则
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QPushButton, QListWidget, QListWidgetItem,
                              QLabel, QLineEdit, QCheckBox, QGroupBox,
                              QTextEdit, QDialog, QDialogButtonBox,
                              QFormLayout, QMessageBox, QMenu, QSplitter)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QAction, QCursor

from src.common.protocol import (TYPE_ACK, ACTION_ADD_MONITOR,
                                  ACTION_REMOVE_MONITOR, ACTION_LIST_MONITORS,
                                  ACTION_UPDATE_FILTERS)
from src.common.logger import get_logger

log = get_logger("monitor_panel")

EVENT_TYPES = [
    "PushEvent", "CreateEvent", "ReleaseEvent",
    "IssuesEvent", "IssueCommentEvent",
    "PullRequestEvent", "PullRequestReviewEvent",
    "WatchEvent", "ForkEvent",
]


class FilterDialog(QDialog):
    """过滤规则编辑对话框"""

    def __init__(self, target: str, current_filters: dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"过滤规则 — {target}")
        self.setMinimumWidth(450)
        self.setModal(True)
        self._filters = current_filters or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 事件类型多选
        type_group = QGroupBox("推送的事件类型 (留空=全部)")
        type_layout = QVBoxLayout(type_group)
        self._type_checks = {}
        allowed = self._filters.get("event_types", [])
        for et in EVENT_TYPES:
            cb = QCheckBox(et)
            cb.setChecked(et in allowed)
            type_layout.addWidget(cb)
            self._type_checks[et] = cb
        layout.addWidget(type_group)

        # 关键词过滤
        kw_group = QGroupBox("关键词过滤 (逗号分隔, 留空=不过滤)")
        kw_layout = QVBoxLayout(kw_group)
        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("例如: bug, security, breaking")
        self.keyword_input.setText(", ".join(self._filters.get("keywords", [])))
        kw_layout.addWidget(self.keyword_input)
        kw_group.setLayout(kw_layout)
        layout.addWidget(kw_group)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_filters(self) -> dict:
        selected_types = [
            et for et, cb in self._type_checks.items() if cb.isChecked()
        ]
        kw_text = self.keyword_input.text().strip()
        keywords = [kw.strip() for kw in kw_text.split(",") if kw.strip()] if kw_text else []

        filters = {}
        if selected_types:
            filters["event_types"] = selected_types
        if keywords:
            filters["keywords"] = keywords
        return filters


class MonitorPanel(QWidget):
    """监控管理面板"""

    monitor_added = pyqtSignal(str, str)  # target, type
    monitor_removed = pyqtSignal(int)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self._monitors = []

        self.client.message_received.connect(self._on_message)
        self._setup_ui()
        self._load_monitors()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title = QLabel("🎯 定点监控")
        title.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        layout.addWidget(title)

        # 添加区域
        add_layout = QHBoxLayout()
        self.target_input = QLineEdit()
        self.target_input.setPlaceholderText("输入用户名 (torvalds) 或仓库 (torvalds/linux)")
        self.target_input.setFont(QFont("Consolas", 10))
        self.target_input.returnPressed.connect(self._add_monitor)
        add_layout.addWidget(self.target_input, 1)

        self.add_btn = QPushButton("➕ 添加监控")
        self.add_btn.clicked.connect(self._add_monitor)
        add_layout.addWidget(self.add_btn)

        layout.addLayout(add_layout)

        # 提示
        hint = QLabel("💡 支持监控用户动态和仓库事件")
        hint.setStyleSheet("color: #888; font-size: 11px; padding-left: 4px;")
        layout.addWidget(hint)

        # 列表
        self.monitor_list = QListWidget()
        self.monitor_list.setAlternatingRowColors(True)
        self.monitor_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.monitor_list.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.monitor_list, 1)

    # ─── 监控操作 ────────────────────────────

    def _add_monitor(self):
        target = self.target_input.text().strip()
        if not target:
            return

        self.target_input.setEnabled(False)
        self.add_btn.setEnabled(False)
        self.add_btn.setText("验证中...")

        self.client.send_command(ACTION_ADD_MONITOR, target=target)

    def _remove_monitor(self, mid: int):
        self.client.send_command(ACTION_REMOVE_MONITOR, monitor_id=mid)

    def _load_monitors(self):
        self.client.send_command(ACTION_LIST_MONITORS)

    def _edit_filters(self, mid: int, target: str, current_filters: dict):
        dialog = FilterDialog(target, current_filters, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_filters = dialog.get_filters()
            self.client.send_command(
                ACTION_UPDATE_FILTERS, monitor_id=mid, filters=new_filters
            )

    # ─── 消息处理 ────────────────────────────

    def _on_message(self, msg_type: str, data: dict):
        if msg_type == TYPE_ACK:
            action = data.get("action", "")
            if action == ACTION_ADD_MONITOR:
                self._handle_add_result(data)
            elif action == ACTION_REMOVE_MONITOR:
                self._handle_remove_result(data)
            elif action == ACTION_LIST_MONITORS:
                self._handle_list_result(data)
            elif action == ACTION_UPDATE_FILTERS:
                if data.get("success"):
                    self._load_monitors()

    def _handle_add_result(self, data: dict):
        self.target_input.setEnabled(True)
        self.add_btn.setEnabled(True)
        self.add_btn.setText("➕ 添加监控")

        if data.get("success"):
            self.target_input.clear()
            self._load_monitors()
            target = data.get("target", "")
            self.monitor_added.emit(target, "repo" if "/" in target else "user")
        else:
            QMessageBox.warning(
                self, "添加失败",
                data.get("error", "未知错误, 请检查目标名称或 Token 是否有效")
            )

    def _handle_remove_result(self, data: dict):
        if data.get("success"):
            self._load_monitors()

    def _handle_list_result(self, data: dict):
        monitors = data.get("monitors", [])
        self._monitors = monitors
        self.monitor_list.clear()

        if not monitors:
            item = QListWidgetItem("  暂无监控目标，在上方输入后添加")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.monitor_list.addItem(item)
            return

        for mon in monitors:
            target = mon.get("target", "")
            mtype = mon.get("type", "repo")
            added = mon.get("added_at", "")[:16]
            filters = mon.get("filters", {})

            filter_info = ""
            if filters.get("event_types"):
                filter_info += f" [{','.join(filters['event_types'][:3])}]"
            if filters.get("keywords"):
                filter_info += f" kw:{','.join(filters['keywords'][:2])}"

            text = f"  [{mtype.upper()}] {target}  📅 {added}{filter_info}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, mon)
            self.monitor_list.addItem(item)

    # ─── 右键菜单 ────────────────────────────

    def _show_context_menu(self, pos):
        item = self.monitor_list.itemAt(pos)
        if not item:
            return
        mon = item.data(Qt.ItemDataRole.UserRole)
        if not mon:
            return

        menu = QMenu(self)

        edit_filter = QAction("🔧 编辑过滤规则", self)
        edit_filter.triggered.connect(
            lambda: self._edit_filters(mon["id"], mon["target"], mon.get("filters", {})))
        menu.addAction(edit_filter)

        menu.addSeparator()

        remove = QAction("🗑 删除监控", self)
        remove.triggered.connect(lambda: self._remove_monitor(mon["id"]))
        menu.addAction(remove)

        menu.exec(QCursor.pos())

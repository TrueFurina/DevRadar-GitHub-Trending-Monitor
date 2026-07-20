"""
DevRadar 主窗口 — 应用入口
整合所有面板, 系统托盘, 通知, 菜单栏
"""

import sys
import threading
from datetime import datetime

from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout,
                              QHBoxLayout, QSplitter, QStatusBar,
                              QMenuBar, QMenu, QSystemTrayIcon,
                              QApplication, QMessageBox, QTextEdit,
                              QPushButton, QLabel, QComboBox,
                              QDialog, QDialogButtonBox, QFrame,
                              QToolTip, QInputDialog)
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import (QFont, QAction, QIcon, QPixmap, QColor,
                          QDesktopServices, QPalette)

from src.common.config import config
from src.common.logger import get_logger
from src.common import protocol as proto
from src.client.client import DevRadarClient
from src.client.panels.search_panel import SearchPanel
from src.client.panels.trending_panel import TrendingPanel
from src.client.panels.monitor_panel import MonitorPanel
from src.client.panels.stream_panel import StreamPanel
from src.client.panels.insight_dialog import InsightDialog

log = get_logger("main_window")

# ─── 深色主题样式表 ─────────────────────
DARK_STYLE = """
QMainWindow, QDialog, QWidget {
    background-color: #1e1e1e;
    color: #dcdcdc;
    font-family: "Consolas", "Cascadia Code", "Fira Code", monospace;
}
QLineEdit {
    background-color: #2d2d2d;
    color: #dcdcdc;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px 8px;
}
QLineEdit:focus {
    border-color: #007acc;
}
QPushButton {
    background-color: #0e639c;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 5px 14px;
    min-height: 24px;
}
QPushButton:hover {
    background-color: #1177bb;
}
QPushButton:disabled {
    background-color: #333;
    color: #666;
}
QComboBox {
    background-color: #2d2d2d;
    color: #dcdcdc;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 4px 8px;
}
QComboBox::drop-down {
    background-color: #333;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #dcdcdc;
    selection-background-color: #0e639c;
}
QListWidget {
    background-color: #252526;
    color: #dcdcdc;
    border: 1px solid #333;
    border-radius: 4px;
    outline: none;
}
QListWidget::item {
    padding: 6px 4px;
    border-bottom: 1px solid #2a2a2a;
}
QListWidget::item:selected {
    background-color: #094771;
    color: white;
}
QListWidget::item:alternate {
    background-color: #2a2a2a;
}
QStatusBar {
    background-color: #007acc;
    color: white;
    font-size: 12px;
}
QStatusBar::item {
    border: none;
}
QMenuBar {
    background-color: #252526;
    color: #dcdcdc;
    border-bottom: 1px solid #333;
}
QMenuBar::item:selected {
    background-color: #094771;
}
QMenu {
    background-color: #252526;
    color: #dcdcdc;
    border: 1px solid #444;
}
QMenu::item:selected {
    background-color: #094771;
}
QToolTip {
    background-color: #333;
    color: #dcdcdc;
    border: 1px solid #555;
    padding: 4px;
}
QCheckBox {
    color: #dcdcdc;
}
QGroupBox {
    border: 1px solid #444;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 12px;
    color: #dcdcdc;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QSplitter::handle {
    background-color: #333;
    width: 2px;
}
QScrollBar:vertical {
    background: #252526;
    width: 10px;
}
QScrollBar::handle:vertical {
    background: #444;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""


def apply_dark_theme(app: QApplication):
    """应用深色主题"""
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    # 调色板
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#dcdcdc"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#252526"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#dcdcdc"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#0e639c"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("white"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#007acc"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    app.setPalette(palette)


class MainWindow(QMainWindow):
    """DevRadar 主窗口"""

    def __init__(self):
        super().__init__()
        self.client = DevRadarClient(self)
        self._setup_windows()

        # 界面
        self._setup_ui()
        self._setup_menu()
        self._setup_tray()
        self._setup_connections()

        # 连接服务端
        self.client.start()

        # 定时更新状态
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_rate_status)
        self._status_timer.start(60_000)  # 每分钟

        log.info("DevRadar 主窗口已启动")

    def _setup_windows(self):
        self.setWindowTitle("DevRadar — GitHub 热门项目与开发者动态追踪器")
        self.setMinimumSize(1280, 800)
        self.resize(1400, 900)

        # 居中
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 4, 8, 4)

        # 搜索栏 (顶部)
        self.search_panel = SearchPanel(self.client, self)
        main_layout.addWidget(self.search_panel)

        # 主分割区域: 左侧 (趋势+监控) | 右侧 (消息流)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        left_splitter = QSplitter(Qt.Orientation.Vertical)

        # 趋势榜单
        self.trending_panel = TrendingPanel(self.client, self)
        left_splitter.addWidget(self.trending_panel)

        # 监控管理
        self.monitor_panel = MonitorPanel(self.client, self)
        left_splitter.addWidget(self.monitor_panel)

        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 2)

        splitter.addWidget(left_splitter)

        # 右侧消息流
        self.stream_panel = StreamPanel(self)
        splitter.addWidget(self.stream_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        main_layout.addWidget(splitter, 1)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.connection_status = QLabel("⚪ 连接中...")
        self.status_bar.addWidget(self.connection_status)

        self.rate_status = QLabel("API: --")
        self.status_bar.addPermanentWidget(self.rate_status)

        self.db_stats = QLabel("")
        self.status_bar.addPermanentWidget(self.db_stats)

    # ─── 菜单栏 ──────────────────────────────

    def _setup_menu(self):
        menubar = self.menuBar()

        # 文件
        file_menu = menubar.addMenu("📁 文件")
        gen_report = QAction("📋 生成简报", self)
        gen_report.setShortcut("Ctrl+R")
        gen_report.triggered.connect(self._generate_report)
        file_menu.addAction(gen_report)

        file_menu.addSeparator()

        exit_action = QAction("❌ 退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 监控
        monitor_menu = menubar.addMenu("🎯 监控")
        refresh_mon = QAction("🔄 刷新监控列表", self)
        refresh_mon.triggered.connect(lambda: self.client.send_command("list_monitors"))
        monitor_menu.addAction(refresh_mon)

        # 工具
        tools_menu = menubar.addMenu("🔧 工具")
        insight_action = QAction("📊 查看项目洞察", self)
        insight_action.triggered.connect(self._show_insight_dialog)
        tools_menu.addAction(insight_action)

        tools_menu.addSeparator()

        settings = QAction("⚙ 设置", self)
        settings.triggered.connect(self._show_settings)
        tools_menu.addAction(settings)

        # 帮助
        help_menu = menubar.addMenu("❓ 帮助")
        about = QAction("ℹ 关于 DevRadar", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)

    # ─── 系统托盘 ────────────────────────────

    def _setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        # 创建简单图标 (由于无图标文件, 使用 QPixmap 画一个)
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor("#007acc"))
        self.tray_icon.setIcon(QIcon(pixmap))
        self.tray_icon.setToolTip("DevRadar")

        tray_menu = QMenu(self)
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.showNormal)
        tray_menu.addAction(show_action)

        report_action = QAction("生成简报", self)
        report_action.triggered.connect(self._generate_report)
        tray_menu.addAction(report_action)

        tray_menu.addSeparator()
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.quit)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    # ─── 信号连接 ────────────────────────────

    def _setup_connections(self):
        # 客户端连接
        self.client.connected.connect(self._on_connected)
        self.client.disconnected.connect(self._on_disconnected)
        self.client.message_received.connect(self._on_message)
        self.client.status_changed.connect(self._on_status)
        self.client.error_occurred.connect(self._on_error)

        # 面板间信号
        self.search_panel.add_monitor_requested.connect(self._add_monitor)
        self.search_panel.bookmark_requested.connect(self._add_bookmark)
        self.search_panel.open_url_requested.connect(self._open_url)

        self.trending_panel.add_monitor_requested.connect(self._add_monitor)
        self.trending_panel.bookmark_requested.connect(self._add_bookmark)
        self.trending_panel.open_url_requested.connect(self._open_url)
        self.trending_panel.view_insight_requested.connect(self._show_insight_for_repo)

        self.monitor_panel.monitor_added.connect(self._on_monitor_added)

        self.stream_panel.unread_count_changed.connect(self._update_tray_badge)

    # ─── 信号处理 ────────────────────────────

    def _on_connected(self):
        self.connection_status.setText("🟢 已连接")
        self.connection_status.setStyleSheet("color: #4EC9B0;")
        self.stream_panel.set_connected(True)
        log.info("已连接到服务端")

    def _on_disconnected(self, reason: str):
        self.connection_status.setText(f"🔴 已断开: {reason}")
        self.connection_status.setStyleSheet("color: #FF4444;")
        self.stream_panel.set_connected(False)
        log.info("已经断开连接: %s", reason)

    def _on_message(self, msg_type: str, data: dict):
        if msg_type == proto.TYPE_NEW_EVENT:
            event = data.get("event", {})
            monitor_id = data.get("monitor_id", 0)
            self.stream_panel.add_event(event)

            # 桌面通知
            if config.get("notification_enabled", True):
                self._show_notification(
                    f"🔔 {event.get('type', '事件')}",
                    event.get("summary", event.get("repo_name", "")),
                )

        elif msg_type == proto.TYPE_ACK:
            action = data.get("action", "")
            if action == proto.ACTION_GET_INSIGHT:
                self._handle_insight_result(data)

        elif msg_type == proto.TYPE_REPORT_RESULT:
            self._handle_report_result(data)

        elif msg_type == proto.TYPE_STATUS:
            self._on_status(data.get("code", ""), data.get("message", ""))

    def _on_status(self, code: str, message: str):
        if code == "rate_limit":
            self.rate_status.setText(f"⚠ {message}")
            self.rate_status.setStyleSheet("color: #FF8800;")
        elif code == "error":
            self.rate_status.setText(f"✗ {message}")
            self.rate_status.setStyleSheet("color: #FF4444;")
        else:
            self.rate_status.setText(message)

    def _on_error(self, message: str):
        log.error("客户端错误: %s", message)
        QMessageBox.warning(self, "错误", message)

    def _update_rate_status(self):
        self.client.send_command(proto.ACTION_GET_RATE_LIMIT)

    # ─── 功能操作 ────────────────────────────

    def _add_monitor(self, target: str, mtype: str):
        self.monitor_panel.target_input.setText(target)
        self.monitor_panel._add_monitor()

    def _add_bookmark(self, full_name: str, url: str, desc: str,
                      language: str, stars: int):
        self.client.send_command(
            proto.ACTION_BOOKMARK_ADD,
            repo_full_name=full_name, url=url,
            description=desc, language=language,
            stars=stars,
        )
        self.status_bar.showMessage(f"⭐ 已收藏: {full_name}", 3000)

    def _open_url(self, url: str):
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _on_monitor_added(self, target: str, mtype: str):
        self.status_bar.showMessage(f"🔔 监控已添加: {target}", 3000)

    def _update_tray_badge(self, count: int):
        if count > 0:
            self.tray_icon.setToolTip(f"DevRadar — {count} 条未读事件")
        else:
            self.tray_icon.setToolTip("DevRadar")

    def _show_notification(self, title: str, message: str):
        """显示系统通知"""
        if hasattr(self, 'tray_icon') and self.tray_icon.supportsMessages():
            self.tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 4000)

    # ─── 简报生成 ────────────────────────────

    def _generate_report(self):
        # 弹窗选择周期
        dialog = QDialog(self)
        dialog.setWindowTitle("生成技术简报")
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("选择简报周期:"))
        period_combo = QComboBox()
        period_combo.addItems(["每日", "每周", "每月"])
        period_combo.setItemData(0, "daily")
        period_combo.setItemData(1, "weekly")
        period_combo.setItemData(2, "monthly")
        layout.addWidget(period_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        period = period_combo.currentData()
        lang = config.get("default_language", "python")
        self.status_bar.showMessage("📋 正在生成简报...")
        self.client.send_command(proto.ACTION_GENERATE_REPORT,
                                 period=period, language=lang)

    def _handle_report_result(self, data: dict):
        """显示生成的简报"""
        content = data.get("content", "")
        period = data.get("period", "weekly")

        dialog = QDialog(self)
        dialog.setWindowTitle(f"📋 DevRadar 简报 ({period})")
        dialog.setMinimumSize(700, 600)

        layout = QVBoxLayout(dialog)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(content)
        text.setFont(QFont("Consolas", 10))
        layout.addWidget(text, 1)

        btn_layout = QHBoxLayout()

        copy_btn = QPushButton("📋 复制到剪贴板")
        copy_btn.clicked.connect(lambda: self._copy_text(content))
        btn_layout.addWidget(copy_btn)

        save_btn = QPushButton("💾 保存为 .md")
        save_btn.clicked.connect(lambda: self._save_report(content, period))
        btn_layout.addWidget(save_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        dialog.exec()

        self._show_notification("📋 简报已生成", f"{period} 简报已准备就绪")
        self.status_bar.showMessage("📋 简报已生成", 3000)

    def _copy_text(self, text: str):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
        self.status_bar.showMessage("📋 已复制到剪贴板", 2000)

    def _save_report(self, content: str, period: str):
        from PyQt6.QtWidgets import QFileDialog
        default_name = f"DevRadar_简报_{datetime.now().strftime('%Y%m%d')}.md"
        path, _ = QFileDialog.getSaveFileName(
            self, "保存简报", default_name,
            "Markdown (*.md);;所有文件 (*)"
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.status_bar.showMessage(f"💾 简报已保存: {path}", 3000)

    # ─── 项目洞察 ────────────────────────────

    def _show_insight_dialog(self):
        repo, ok = QInputDialog.getText(self, "项目洞察", "输入仓库全名 (如 torvalds/linux):")
        if ok and repo:
            self._show_insight_for_repo(repo.strip())

    _pending_insight_dialog = None

    def _show_insight_for_repo(self, repo: str):
        dialog = InsightDialog(repo, client=self.client, parent=self)
        self._pending_insight_dialog = dialog
        dialog.exec()

    def _handle_insight_result(self, data: dict):
        """处理洞察数据并传递给打开的弹窗"""
        if self._pending_insight_dialog:
            self._pending_insight_dialog.display_insight(data)
            self._pending_insight_dialog = None

    # ─── 设置 ────────────────────────────────

    def _show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("⚙ DevRadar 设置")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("默认编程语言:"))
        lang_edit = QComboBox()
        lang_edit.addItems(["python", "java", "go", "javascript", "typescript", "rust", "all"])
        lang_edit.setCurrentText(config.get("default_language", "python"))
        layout.addWidget(lang_edit)

        layout.addWidget(QLabel("轮询间隔 (秒):"))
        poll_edit = QComboBox()
        poll_edit.addItems(["60", "120", "300", "600"])
        poll_edit.setCurrentText(str(config.get("poll_interval_seconds", 300)))
        layout.addWidget(poll_edit)

        layout.addWidget(QLabel("预警阈值 (单日 Star 增长 >):"))
        threshold_edit = QComboBox()
        threshold_edit.addItems(["50", "100", "500", "1000", "5000"])
        layout.addWidget(threshold_edit)

        layout.addWidget(QLabel("简报周期:"))
        report_combo = QComboBox()
        report_combo.addItems(["weekly", "daily", "monthly"])
        report_combo.setCurrentText(config.get("report_period", "weekly"))
        layout.addWidget(report_combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(lambda: self._save_settings(dialog, lang_edit, poll_edit, report_combo))
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def _save_settings(self, dialog, lang_combo, poll_combo, report_combo):
        config.set("default_language", lang_combo.currentText().lower())
        config.set("poll_interval_seconds", int(poll_combo.currentText()))
        config.set("report_period", report_combo.currentText())
        config.save()
        self.status_bar.showMessage("⚙ 设置已保存", 3000)
        dialog.accept()

    # ─── About ───────────────────────────────

    def _show_about(self):
        QMessageBox.about(
            self, "关于 DevRadar",
            "<h2>DevRadar</h2>"
            "<p>GitHub 热门项目与开发者动态追踪器</p>"
            "<p>版本 1.0.0</p>"
            "<hr>"
            "<p>技术栈:</p>"
            "<ul>"
            "<li>GUI: PyQt6</li>"
            "<li>通信: TCP Socket</li>"
            "<li>数据: SQLite + GitHub API</li>"
            "<li>爬虫: BeautifulSoup4</li>"
            "</ul>"
            "<p><i>网络编程与应用课程设计</i></p>"
        )

    # ─── 窗口事件 ────────────────────────────

    def closeEvent(self, event):
        """关闭窗口时清理"""
        self.client.stop()
        self.tray_icon.hide()
        event.accept()

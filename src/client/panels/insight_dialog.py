"""
项目洞察面板 —  Star 增长曲线 + 健康度指标
"""

from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QTextEdit, QFrame,
                              QScrollArea, QWidget, QGridLayout,
                              QMessageBox)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor

from src.common.logger import get_logger
from src.common import protocol as proto

log = get_logger("insight")

# 尝试导入 matplotlib (可选)
try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    log.warning("matplotlib 未安装, 图表功能不可用")


class StarChartWidget(QWidget):
    """Star 增长曲线图 (嵌入 matplotlib)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(250)

        if not MATPLOTLIB_AVAILABLE:
            layout = QVBoxLayout(self)
            label = QLabel("📊 图表: matplotlib 未安装\npip install matplotlib")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #888; font-size: 13px;")
            layout.addWidget(label)
            return

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.figure = Figure(figsize=(6, 2.5), dpi=100)
        self.figure.patch.set_facecolor("#1e1e1e")

        self.canvas = FigureCanvas(self.figure)
        self.canvas.setStyleSheet("background: transparent;")
        layout.addWidget(self.canvas)

        self.ax = self.figure.add_subplot(111)
        self._setup_style()

    def _setup_style(self):
        """设置深色主题"""
        if not MATPLOTLIB_AVAILABLE:
            return
        self.ax.set_facecolor("#252526")
        self.ax.tick_params(colors="#dcdcdc", labelsize=9)
        self.ax.spines["bottom"].set_color("#444")
        self.ax.spines["top"].set_color("#444")
        self.ax.spines["left"].set_color("#444")
        self.ax.spines["right"].set_color("#444")
        self.ax.xaxis.label.set_color("#dcdcdc")
        self.ax.yaxis.label.set_color("#dcdcdc")
        self.ax.title.set_color("#dcdcdc")

    def plot_star_history(self, star_data: list[dict], collecting_msg: str = ""):
        """绘制 Star 历史曲线"""
        if not MATPLOTLIB_AVAILABLE:
            return

        self.ax.clear()
        self._setup_style()

        if not star_data or len(star_data) < 2:
            self.ax.text(0.5, 0.5, collecting_msg or "数据积累中...",
                         ha="center", va="center", color="#888", fontsize=13,
                         transform=self.ax.transAxes)
            self.canvas.draw()
            return

        dates = []
        stars = []
        for s in star_data:
            try:
                dt = datetime.fromisoformat(str(s.get("date", s.get("recorded_at", ""))))
                dates.append(dt)
                stars.append(s.get("stars", s.get("star_count", 0)))
            except (ValueError, TypeError):
                continue

        if len(dates) < 2:
            self.ax.text(0.5, 0.5, collecting_msg or "数据不足, 继续收集中...",
                         ha="center", va="center", color="#888", fontsize=13,
                         transform=self.ax.transAxes)
            self.canvas.draw()
            return

        self.ax.plot(dates, stars, color="#007acc", linewidth=2, marker="o", markersize=4)
        self.ax.fill_between(dates, stars, alpha=0.15, color="#007acc")

        # 格式化
        if len(dates) > 1:
            self.ax.set_xlim(dates[0], dates[-1])
        self.ax.set_ylabel("⭐ Stars")
        self.ax.set_title("Star 增长趋势", fontsize=11)

        self.figure.tight_layout()
        self.canvas.draw()

    def show_collecting(self, days: int = 1, target_days: int = 7):
        """显示数据收集进度"""
        if not MATPLOTLIB_AVAILABLE:
            return
        self.ax.clear()
        self._setup_style()
        msg = f"数据收集中 (已记录 {days}/{target_days} 天)"
        self.ax.text(0.5, 0.5, msg, ha="center", va="center",
                     color="#FF8800", fontsize=13,
                     transform=self.ax.transAxes)
        self.canvas.draw()


class InsightDialog(QDialog):
    """项目洞察弹窗"""

    def __init__(self, repo_full_name: str, client=None, parent=None):
        super().__init__(parent)
        self.repo_full_name = repo_full_name
        self._client = client  # 直接持有 client 引用, 不再遍历 parent 树
        self._insight_data = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # 标题
        title = QLabel(f"📊 {self.repo_full_name}")
        title.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("color: #444;")
        layout.addWidget(separator)

        # Star 图表
        self.chart = StarChartWidget(self)
        layout.addWidget(self.chart)

        # 健康度信息
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        self.health_layout = QGridLayout(scroll_widget)
        self.health_layout.setSpacing(8)
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        # 关闭按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        # 加载数据
        self._load_insight()

    def _load_insight(self):
        """从服务端获取洞察数据"""
        if self._client:
            self._client.send_command(proto.ACTION_GET_INSIGHT, repo=self.repo_full_name)

        # 延迟等待数据
        QTimer.singleShot(500, self._check_response)

    def _check_response(self):
        """检查是否有响应数据 (实际通过信号接收)"""
        if self._insight_data:
            self._display_data()

    def display_insight(self, data: dict):
        """由主窗口调用, 传入服务端返回的洞察数据"""
        self._insight_data = data
        self._display_data()

    def _display_data(self):
        """渲染洞察数据到界面"""
        if not self._insight_data:
            return

        # 图表示
        star_history = self._insight_data.get("star_history", [])
        collecting = self._insight_data.get("data_collecting", False)
        collecting_msg = self._insight_data.get("data_collecting_msg", "")

        if collecting:
            days = self._insight_data.get("star_history_days", 0)
            self.chart.show_collecting(days)
        else:
            self.chart.plot_star_history(star_history, collecting_msg)

        # 健康度
        health = self._insight_data.get("health", {})
        if health.get("error"):
            row = self.health_layout.rowCount()
            self.health_layout.addWidget(QLabel(f"⚠ {health['error']}"), row, 0, 1, 2)
            return

        row = self.health_layout.rowCount()
        items = [
            ("🏷 语言", health.get("language", "-")),
            ("⭐ 总 Star", f"{health.get('stars', 0):,}"),
            ("🍴 Forks", f"{health.get('forks', 0):,}"),
            ("👁 Watchers", f"{health.get('watchers', 0):,}"),
            ("🕐 最后提交", str(health.get("last_commit", ""))[:10]),
            ("📦 开源协议", health.get("license", "无")),
            ("👥 活跃贡献者", str(health.get("active_contributors", 0))),
            ("📅 创建时间", str(health.get("created_at", ""))[:10]),
        ]

        for label, value in items:
            l = QLabel(label)
            l.setStyleSheet("color: #888;")
            v = QLabel(str(value))
            v.setStyleSheet("color: #dcdcdc; font-weight: bold;")
            self.health_layout.addWidget(l, row, 0, Qt.AlignmentFlag.AlignLeft)
            self.health_layout.addWidget(v, row, 1, Qt.AlignmentFlag.AlignLeft)
            row += 1

        # Issue 关闭率 (如果有数据)
        open_issues = health.get("open_issues", 0)
        if open_issues is not None:
            l = QLabel("🐛 当前 Open Issues")
            l.setStyleSheet("color: #888;")
            v = QLabel(f"{open_issues}")
            v.setStyleSheet("color: #FF8800;" if open_issues > 50 else "color: #4EC9B0;")
            self.health_layout.addWidget(l, row, 0, Qt.AlignmentFlag.AlignLeft)
            self.health_layout.addWidget(v, row, 1, Qt.AlignmentFlag.AlignLeft)
            row += 1

        # 热门话题
        topics = health.get("topics", [])
        if topics:
            l = QLabel("🏷 话题标签")
            l.setStyleSheet("color: #888;")
            v = QLabel(", ".join(topics[:8]))
            v.setStyleSheet("color: #007acc;")
            v.setWordWrap(True)
            self.health_layout.addWidget(l, row, 0, Qt.AlignmentFlag.AlignTop)
            self.health_layout.addWidget(v, row, 1, Qt.AlignmentFlag.AlignLeft)
            row += 1

        self.health_layout.setRowStretch(row, 1)

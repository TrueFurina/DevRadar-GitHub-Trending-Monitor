#!/usr/bin/env python3
"""
DevRadar 一键启动脚本
自动: 启动服务端 → 启动 GUI → 退出时清理
"""

import sys
import time
import signal
import os

# 确保项目根目录在 sys.path 中
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

# Windows 终端编码兼容: 尝试切 UTF-8, 失败则忽略
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, UnicodeDecodeError):
    pass


def main():
    """启动 DevRadar 应用"""
    # 导入
    from src.common.config import config
    from src.common.logger import get_logger

    log = get_logger("launcher")

    # 检查配置
    if not config.has_token():
        print("=" * 60)
        print("  DevRadar — GitHub 热门项目与开发者动态追踪器")
        print("=" * 60)
        print()
        print("  ⚠ 未配置 GitHub Token")
        print()
        print("  部分功能 (搜索/API 调用) 会受到限制 (60次/小时 → 10次/小时)")
        print()
        print("  建议在环境变量中设置 GITHUB_TOKEN:")
        print("    set GITHOKEN=ghp_xxxxxxxxxxxx")
        print()
        print("  或创建 data/config.json 添加 github_token 字段")
        print()
        print("  按 Enter 继续 (或 Ctrl+C 退出)...")
        try:
            input()
        except KeyboardInterrupt:
            print("\n已取消")
            return

    print("🚀 DevRadar 正在启动...")
    log.info("=" * 50)
    log.info("DevRadar 启动中")
    log.info("=" * 50)

    # ─── 启动服务端 (子线程) ──────────────
    import threading
    from src.server.server import DevRadarServer
    from src.server.monitor_scheduler import MonitorScheduler
    from src.server.snapshot_manager import snapshot_manager

    server = DevRadarServer()

    # 创建调度器 (注入发送回调)
    scheduler = MonitorScheduler(send_callback=server.send)

    def run_server():
        """在子线程中启动服务端"""
        server.start()

    server_thread = threading.Thread(target=run_server, daemon=True, name="server-main")
    server_thread.start()

    # 等待服务端就绪
    time.sleep(0.5)

    # 启动调度器
    scheduler.start()
    snapshot_manager.start()

    # ─── 启动 GUI ─────────────────────────
    from PyQt6.QtWidgets import QApplication
    from src.client.main_window import MainWindow, apply_dark_theme

    app = QApplication(sys.argv)
    apply_dark_theme(app)
    app.setApplicationName("DevRadar")
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()

    log.info("GUI 已启动")

    # 退出时清理
    exit_code = app.exec()

    log.info("正在关闭 DevRadar...")
    scheduler.stop()
    snapshot_manager.stop()
    server.stop()

    log.info("DevRadar 已退出")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

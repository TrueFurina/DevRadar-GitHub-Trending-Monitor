"""
Star 快照管理器 — 定期采集监控仓库的 Star 数据
"""

import threading
import time
from datetime import datetime
from typing import Optional

from src.common.config import config
from src.common.logger import get_logger
from src.server.db_manager import db
from src.server.github_api import api, GitHubAPIError

log = get_logger("snapshot")


class SnapshotManager:
    """Star 快照调度器"""

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="snapshot-manager")
        self._thread.start()
        log.info("Star 快照管理器已启动")

    def stop(self):
        self._running = False
        log.info("Star 快照管理器已停止")

    def _loop(self):
        interval_hours = config.get("snapshot_interval_hours", 6)
        interval_seconds = interval_hours * 3600

        # 延迟首次执行，给其他模块启动时间
        time.sleep(30)

        while self._running:
            try:
                self._take_snapshot()
            except Exception as e:
                log.error("快照异常: %s", e)

            # 等待间隔
            for _ in range(int(interval_seconds)):
                if not self._running:
                    return
                time.sleep(1)

    def _take_snapshot(self):
        """对所有被监控的仓库做 Star 快照"""
        monitors = db.get_monitors()
        repo_names = set()
        for mon in monitors:
            if mon["type"] == "repo":
                repo_names.add(mon["target"])
            elif mon["type"] == "user":
                # 用户类型的监控: 尝试获取其仓库
                try:
                    repos = api.get_user_repos(mon["target"], per_page=20)
                    for r in repos:
                        full_name = r.get("full_name", "")
                        if full_name:
                            repo_names.add(full_name)
                except GitHubAPIError:
                    continue

        if not repo_names:
            log.debug("无仓库需要快照")
            return

        # 同时从 trending_cache 中收集热门仓库
        trending = db.get_trending_cache("all", "daily")
        for item in trending:
            fn = item.get("repo_full_name", "")
            if fn:
                repo_names.add(fn)

        count = 0
        for repo_name in repo_names:
            if not self._running:
                return

            try:
                repo_info = api.get_repo(repo_name)
                stars = repo_info.get("stargazers_count", 0)
                db.save_star_snapshot(repo_name, stars)
                count += 1
            except GitHubAPIError:
                continue
            except Exception as e:
                log.warning("快照 %s 失败: %s", repo_name, e)

            # 避免 API 限流
            time.sleep(0.5)

        log.info("Star 快照完成: %d 个仓库", count)

    def snapshot_now(self):
        """手动立即执行"""
        self._take_snapshot()


# 全局实例
snapshot_manager = SnapshotManager()

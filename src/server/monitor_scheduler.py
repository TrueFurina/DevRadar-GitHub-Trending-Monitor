"""
监控调度器 — 定时轮询监控目标的事件并推送
"""

import json
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from src.common.config import config
from src.common.logger import get_logger
from src.common import protocol as proto
from src.server.db_manager import db
from src.server.github_api import api, GitHubAPIError

log = get_logger("scheduler")

# 用户事件中我们关心的类型
INTERESTING_EVENT_TYPES = {
    "PushEvent", "CreateEvent", "ReleaseEvent",
    "IssuesEvent", "IssueCommentEvent",
    "PullRequestEvent", "PullRequestReviewEvent",
    "WatchEvent", "ForkEvent", "DeleteEvent",
    "PublicEvent", "MemberEvent",
}

# 按重要性分级的推送标签
IMPORTANCE_MAP = {
    "ReleaseEvent": "high",
    "PullRequestEvent": "high",
    "IssuesEvent": "medium",
    "PushEvent": "low",
    "WatchEvent": "low",
    "ForkEvent": "low",
}


class MonitorScheduler:
    """定时轮询监控目标"""

    def __init__(self, send_callback):
        """
        send_callback: 推送消息到客户端的函数 (bytes) -> None
        """
        self.send = send_callback
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_check: dict[int, int] = {}  # monitor_id → last_event_id (int)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="monitor-scheduler")
        self._thread.start()
        log.info("监控调度器已启动")

    def stop(self):
        self._running = False
        log.info("监控调度器已停止")

    def _loop(self):
        """主循环"""
        interval = config.get("poll_interval_seconds", 300)

        while self._running:
            try:
                self._poll_all()
            except Exception as e:
                log.error("轮询异常: %s", e, exc_info=True)

            # 等待期间检查 running 变化
            for _ in range(max(interval, 10)):
                if not self._running:
                    return
                time.sleep(1)

    def _poll_all(self):
        """轮询所有监控目标"""
        monitors = db.get_monitors()
        if not monitors:
            return

        for mon in monitors:
            if not self._running:
                return

            # 检查 API 限流
            if api.rate_limit.is_nearly_exhausted():
                log.warning("API 配额不足 (剩余 %s), 暂停轮询", api.rate_limit.remaining)
                self.send(proto.status("rate_limit",
                    f"API 剩余 {api.rate_limit.remaining} 次, 暂停轮询"))
                time.sleep(60)
                continue

            try:
                self._poll_monitor(mon)
            except GitHubAPIError as e:
                log.warning("轮询 %s 失败: %s", mon["target"], e)
                continue
            except Exception as e:
                log.error("轮询 %s 异常: %s", mon["target"], e)

    def _poll_monitor(self, mon: dict):
        """轮询单个监控目标"""
        mid = mon["id"]
        target = mon["target"]
        mtype = mon["type"]
        filters = mon.get("filters", {})

        # 获取事件
        if mtype == "user":
            events = api.get_user_events(target, per_page=30)
        else:
            events = api.get_repo_events(target, per_page=30)

        if not events:
            return

        # 获取已处理的最新事件 ID
        last_id = self._last_check.get(mid, "")
        new_count = 0

        for event in events:
            event_id = str(event.get("id", ""))
            if not event_id:
                continue

            # 跳过已处理的事件 (用整数比较, 避免字符串长度不一致问题)
            if last_id > 0:
                try:
                    if int(event_id) <= last_id:
                        break
                except (ValueError, TypeError):
                    continue

            # 应用过滤规则
            if not self._passes_filter(event, filters):
                continue

            # 持久化
            event_type = event.get("type", "Unknown")
            repo_name = event.get("repo", {}).get("name", "") if isinstance(event.get("repo"), dict) else ""
            actor = event.get("actor", {}).get("login", "") if isinstance(event.get("actor"), dict) else ""
            payload = event.get("payload", {})

            # 构建 URL
            url = self._build_event_url(event)

            db.save_event(mid, event_type, payload, repo_name, actor, url)

            # 推送客户端
            self.send(proto.new_event(mid, {
                "id": event_id,
                "type": event_type,
                "repo_name": repo_name,
                "actor": actor,
                "url": url,
                "importance": IMPORTANCE_MAP.get(event_type, "low"),
                "target": target,
                "created_at": event.get("created_at", ""),
                "summary": self._summarize_event(event),
            }))
            new_count += 1

        if new_count > 0:
            # 更新最后检查的 ID (用整数)
            try:
                self._last_check[mid] = int(events[0].get("id", 0))
            except (ValueError, TypeError):
                pass
            log.info("监控 %s: 发现 %d 个新事件", target, new_count)

    def _passes_filter(self, event: dict, filters: dict) -> bool:
        """检查事件是否通过过滤规则"""
        if not filters:
            return True

        # 事件类型过滤
        allowed_types = filters.get("event_types", [])
        if allowed_types:
            if event.get("type") not in allowed_types:
                return False

        # 关键词过滤
        keywords = filters.get("keywords", [])
        if keywords:
            payload_text = json.dumps(event.get("payload", {})).lower()
            if not any(kw.lower() in payload_text for kw in keywords):
                return False

        return True

    def _summarize_event(self, event: dict) -> str:
        """生成事件摘要"""
        etype = event.get("type", "")
        payload = event.get("payload", {})
        repo = ""
        if isinstance(event.get("repo"), dict):
            repo = event["repo"].get("name", "")
        elif isinstance(event.get("repo"), str):
            repo = event["repo"]

        if etype == "PushEvent":
            commits = payload.get("commits", [])
            count = len(commits)
            msg = commits[0].get("message", "").split("\n")[0] if commits else ""
            return f"推送 {count} 个提交 · {msg[:60]}"
        elif etype == "ReleaseEvent":
            rel = payload.get("release", {})
            return f"发布 {rel.get('tag_name', '')}: {rel.get('name', '')}"
        elif etype == "IssuesEvent":
            action = payload.get("action", "")
            issue = payload.get("issue", {})
            return f"{action.capitalize()} Issue #{issue.get('number', '')}: {issue.get('title', '')}"
        elif etype == "PullRequestEvent":
            action = payload.get("action", "")
            pr = payload.get("pull_request", {})
            return f"{action.capitalize()} PR #{pr.get('number', '')}: {pr.get('title', '')}"
        elif etype == "WatchEvent":
            return f"Star 了仓库 {repo}"
        elif etype == "ForkEvent":
            return f"Fork 了仓库 {repo}"
        elif etype == "CreateEvent":
            ref_type = payload.get("ref_type", "")
            ref = payload.get("ref", "")
            return f"创建 {ref_type}: {ref}"
        elif etype == "IssueCommentEvent":
            issue = payload.get("issue", {})
            return f"评论了 Issue #{issue.get('number', '')}"
        else:
            return f"{etype} 事件"

    def _build_event_url(self, event: dict) -> str:
        """构建事件 URL"""
        etype = event.get("type", "")
        payload = event.get("payload", {})
        repo_name = ""
        if isinstance(event.get("repo"), dict):
            repo_name = event["repo"].get("name", "")

        if etype == "IssuesEvent":
            issue = payload.get("issue", {})
            return issue.get("html_url", "")
        elif etype == "PullRequestEvent":
            pr = payload.get("pull_request", {})
            return pr.get("html_url", "")
        elif etype == "ReleaseEvent":
            rel = payload.get("release", {})
            return rel.get("html_url", "")
        elif etype == "PushEvent":
            commits = payload.get("commits", [])
            if commits:
                return commits[0].get("url", "")
            return f"https://github.com/{repo_name}/commits"
        elif etype == "IssueCommentEvent":
            issue = payload.get("issue", {})
            return issue.get("html_url", "")
        else:
            return f"https://github.com/{repo_name}"

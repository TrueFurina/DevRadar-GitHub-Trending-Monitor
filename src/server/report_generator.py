"""
个人技术简报生成器
数据全部来自本地数据库，无需额外 API 请求
"""

from datetime import datetime, timedelta
from typing import Optional

from src.common.config import config
from src.common.logger import get_logger
from src.server.db_manager import db
from src.server.github_api import api

log = get_logger("report")


def _get_period_range(period: str) -> tuple[datetime, str]:
    """计算周期起止时间, 返回 (since, label)"""
    now = datetime.now()
    if period == "weekly":
        since = now - timedelta(days=7)
        label = "本周"
    elif period == "monthly":
        since = now - timedelta(days=30)
        label = "本月"
    elif period == "daily":
        since = now - timedelta(days=1)
        label = "今日"
    else:
        since = now - timedelta(days=7)
        label = "本周"
    return since, label


def get_insight_data(repo_full_name: str) -> dict:
    """获取项目洞察数据"""
    result = {
        "repo": repo_full_name,
        "star_history": [],
        "health": {},
        "star_history_days": 0,
        "data_collecting": False,
    }

    # 1. Star 历史
    star_data = db.get_star_history(repo_full_name)
    result["star_history"] = [
        {"date": s["recorded_at"], "stars": s["star_count"]}
        for s in star_data
    ]
    result["star_history_days"] = len(star_data)

    if len(star_data) < 7:
        result["data_collecting"] = True
        result["data_collecting_msg"] = f"数据收集中 (已记录 {len(star_data)}/7 天)"

    # 2. 项目健康度 — 从 API 实时获取
    try:
        repo = api.get_repo(repo_full_name)
        result["health"] = {
            "last_commit": repo.get("pushed_at", ""),
            "open_issues": repo.get("open_issues_count", 0),
            "forks": repo.get("forks_count", 0),
            "stars": repo.get("stargazers_count", 0),
            "watchers": repo.get("subscribers_count", 0),
            "description": repo.get("description", ""),
            "language": repo.get("language", ""),
            "license": repo.get("license", {}).get("spdx_id", "") if repo.get("license") else "",
            "created_at": repo.get("created_at", ""),
            "topics": repo.get("topics", []),
        }
    except Exception:
        result["health"] = {"error": "无法获取项目数据"}
        result["fetch_error"] = True

    # 3. 活跃贡献者
    try:
        contributors = api.get_repo_contributors(repo_full_name)
        result["health"]["active_contributors"] = len(contributors)
        result["health"]["top_contributors"] = [
            {"login": c.get("login", ""), "contributions": c.get("contributions", 0)}
            for c in contributors[:5]
        ]
    except Exception:
        result["health"]["active_contributors"] = 0

    return result


def generate_report(period: str = "weekly", language: str = "python") -> str:
    """
    生成 Markdown 格式的技术简报
    参数:
        period: "daily" | "weekly" | "monthly"
        language: 语言过滤, 如 "python", "all"
    返回: Markdown 文本
    """
    since, period_label = _get_period_range(period)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    monitors = db.get_monitors()

    lines = []
    lines.append(f"# 📡 DevRadar 个人技术简报")
    lines.append(f"")
    lines.append(f"**周期**: {period_label} | **生成时间**: {now_str}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # ── 1. 我的关注动态 ──────────────────────
    lines.append(f"## 一、我的关注动态")
    lines.append(f"")

    event_count = 0
    for mon in monitors:
        target = mon["target"]
        events = db.get_events_since(since, mon["id"])

        # 按类型分组
        releases = [e for e in events if e.get("event_type") == "ReleaseEvent"]
        pushes = [e for e in events if e.get("event_type") == "PushEvent"]
        issues = [e for e in events if e.get("event_type") == "IssuesEvent"]
        prs = [e for e in events if e.get("event_type") == "PullRequestEvent"]
        others = [e for e in events if e.get("event_type") not in
                  ("ReleaseEvent", "PushEvent", "IssuesEvent", "PullRequestEvent")]

        if not events:
            continue

        event_count += len(events)
        lines.append(f"### 📌 {target}")
        lines.append(f"")

        if releases:
            lines.append(f"**🚀 重要发布 ({len(releases)})**")
            for e in releases[:5]:
                p = e.get("payload", {})
                if isinstance(p, str):
                    p = {}
                tag = p.get("release", {}).get("tag_name", "") if isinstance(p.get("release"), dict) else ""
                name = p.get("release", {}).get("name", "") if isinstance(p.get("release"), dict) else ""
                url = e.get("url", "")
                lines.append(f"- `{tag}` {name} — [查看发布]({url})")
            lines.append(f"")

        if pushes:
            lines.append(f"**📝 提交更新 ({len(pushes)})**")
            for e in pushes[:8]:
                p = e.get("payload", {})
                if isinstance(p, str):
                    p = {}
                commits = p.get("commits", []) if isinstance(p, dict) else []
                if commits:
                    msg = commits[0].get("message", "").split("\n")[0]
                    sha = commits[0].get("sha", "")[:7]
                    url = commits[0].get("url", "")
                    lines.append(f"- `{sha}` {msg[:80]} — [提交]({url})")
            lines.append(f"")

        if issues:
            lines.append(f"**🐛 新增 Issue ({len(issues)})**")
            for e in issues[:5]:
                p = e.get("payload", {})
                if isinstance(p, str):
                    p = {}
                issue = p.get("issue", {}) if isinstance(p, dict) else {}
                title = issue.get("title", "")
                number = issue.get("number", "")
                state = p.get("action", "opened")
                url = e.get("url", issue.get("html_url", ""))
                lines.append(f"- #{number} [{state}] {title} — [查看]({url})")
            lines.append(f"")

        if prs:
            lines.append(f"**🔀 Pull Request ({len(prs)})**")
            for e in prs[:5]:
                p = e.get("payload", {})
                if isinstance(p, str):
                    p = {}
                pr = p.get("pull_request", {}) if isinstance(p, dict) else {}
                title = pr.get("title", "")
                number = pr.get("number", "")
                state = p.get("action", "opened")
                url = e.get("url", pr.get("html_url", ""))
                lines.append(f"- #{number} [{state}] {title} — [查看]({url})")
            lines.append(f"")

    if event_count == 0:
        lines.append(f"> 🦗 你关注的动态领域还很宁静，快去添加几个大神仓库吧！")
        lines.append(f"")

    # ── 2. 趋势 Top 5 ─────────────────────────
    lines.append(f"## 二、趋势 Top 5")
    lines.append(f"")

    since_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
    trending_lang = language if language and language != "all" else "all"
    cached = db.get_trending_cache(trending_lang, "daily")
    if cached:
        top5 = cached[:5]
        for i, item in enumerate(top5, 1):
            d = item.get("data", {}) if isinstance(item.get("data"), dict) else item
            lines.append(f"{i}. **[{d.get('full_name', '')}]({d.get('url', '')})**")
            lines.append(f"   - ⭐ {d.get('stars', 0)}  🍴 {d.get('forks', 0)}  📈 +{d.get('daily_stars', 0)} today")
            if d.get('description'):
                lines.append(f"   - {d['description'][:100]}")
            lines.append(f"")
    else:
        lines.append(f"> 暂无趋势数据，请在应用中刷新后重试。")
        lines.append(f"")

    # ── 3. 收藏夹 ──────────────────────────────
    lines.append(f"## 三、我的收藏")
    lines.append(f"")

    bookmarks = db.get_bookmarks()
    if bookmarks:
        for bm in bookmarks[:10]:
            lines.append(f"- **[{bm.get('repo_full_name', '')}]({bm.get('repo_url', '')})**")
            desc = bm.get('description', '')
            if desc:
                lines.append(f"  - {desc[:80]}")
            lines.append(f"  - ⭐ {bm.get('stars', 0)}  🖊 {bm.get('language', '')}")
    else:
        lines.append(f"> 收藏夹还是空的，快去发现好项目吧！")
    lines.append(f"")

    # ── 4. 搜索历史 ────────────────────────────
    lines.append(f"## 四、最近搜索")
    lines.append(f"")

    history = db.get_search_history()
    if history:
        for q in history[:5]:
            lines.append(f"- `{q}`")
    else:
        lines.append(f"> 暂无搜索历史。")
    lines.append(f"")

    # ── 尾部 ──────────────────────────────────
    lines.append(f"---")
    lines.append(f"*由 DevRadar 自动生成 | {now_str}*")
    lines.append(f"")

    return "\n".join(lines)

"""
DevRadar 数据持久层 — SQLite 操作封装
线程安全: 每个线程使用独立连接, 写操作通过锁序列化
"""

import sqlite3
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.common.logger import get_logger

log = get_logger("db")

DB_PATH = "data/devradar.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS monitors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target      TEXT    UNIQUE NOT NULL,
    type        TEXT    NOT NULL CHECK(type IN ('user','repo')),
    filters     TEXT    DEFAULT '{}',
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    monitor_id  INTEGER NOT NULL REFERENCES monitors(id) ON DELETE CASCADE,
    event_type  TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    repo_name   TEXT,
    actor       TEXT,
    url         TEXT,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_events_monitor ON events(monitor_id);
CREATE INDEX IF NOT EXISTS idx_events_received ON events(received_at);

CREATE TABLE IF NOT EXISTS trending_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    language    TEXT    NOT NULL,
    since       TEXT    NOT NULL CHECK(since IN ('daily','weekly','monthly')),
    repo_id     TEXT    NOT NULL,
    repo_full_name TEXT NOT NULL,
    data        TEXT    NOT NULL,
    fetched_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_trending_uniq
    ON trending_cache(language, since, repo_id);

CREATE TABLE IF NOT EXISTS star_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name  TEXT    NOT NULL,
    star_count      INTEGER NOT NULL,
    recorded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_star_snapshots_repo
    ON star_snapshots(repo_full_name, recorded_at);

CREATE TABLE IF NOT EXISTS bookmarks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name  TEXT    UNIQUE NOT NULL,
    repo_url        TEXT,
    description     TEXT,
    language        TEXT,
    stars           INTEGER DEFAULT 0,
    note            TEXT    DEFAULT '',
    saved_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS search_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    query       TEXT    NOT NULL,
    searched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_search_history_time
    ON search_history(searched_at DESC);
"""


class DatabaseManager:
    """数据库管理器 — 线程安全"""

    _instance: Optional["DatabaseManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db_path: str = DB_PATH):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.db_path = Path(db_path)
        self._write_lock = threading.Lock()
        # 线程本地存储 — 每个线程使用独立连接
        self._local = threading.local()
        self._init_db()

    # ─── 连接管理 ──────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self):
        """初始化数据库 — 创建表"""
        conn = self._get_conn()
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
        log.info("数据库初始化完成: %s", self.db_path)

    def close(self):
        """关闭当前线程的连接"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None

    def close_all(self):
        """关闭所有连接 (仅在进程退出时调用)"""
        self.close()

    # ─── 监控管理 ──────────────────────────────────

    def add_monitor(self, target: str, mtype: str, filters: dict = None) -> int:
        with self._write_lock:
            conn = self._get_conn()
            try:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO monitors (target, type, filters) VALUES (?,?,?)",
                    (target, mtype, json.dumps(filters or {})),
                )
                conn.commit()
                if cur.rowcount == 0:
                    # 已存在, 返回已有 id
                    row = conn.execute(
                        "SELECT id FROM monitors WHERE target=?", (target,)
                    ).fetchone()
                    return row["id"]
                return cur.lastrowid
            except sqlite3.Error as e:
                log.error("添加监控失败 %s: %s", target, e)
                return -1

    def remove_monitor(self, monitor_id: int) -> bool:
        with self._write_lock:
            try:
                conn = self._get_conn()
                conn.execute("DELETE FROM events WHERE monitor_id=?", (monitor_id,))
                conn.execute("DELETE FROM monitors WHERE id=?", (monitor_id,))
                conn.commit()
                return True
            except sqlite3.Error as e:
                log.error("删除监控失败 id=%s: %s", monitor_id, e)
                return False

    def get_monitors(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, target, type, filters, added_at FROM monitors ORDER BY added_at DESC"
        ).fetchall()
        result = []
        for r in rows:
            m = dict(r)
            m["filters"] = json.loads(m["filters"]) if isinstance(m["filters"], str) else m["filters"]
            result.append(m)
        return result

    def get_monitor(self, monitor_id: int) -> Optional[dict]:
        conn = self._get_conn()
        r = conn.execute(
            "SELECT id, target, type, filters, added_at FROM monitors WHERE id=?",
            (monitor_id,),
        ).fetchone()
        if r:
            m = dict(r)
            m["filters"] = json.loads(m["filters"]) if isinstance(m["filters"], str) else m["filters"]
            return m
        return None

    def update_filters(self, monitor_id: int, filters: dict) -> bool:
        with self._write_lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "UPDATE monitors SET filters=? WHERE id=?",
                    (json.dumps(filters), monitor_id),
                )
                conn.commit()
                return True
            except sqlite3.Error as e:
                log.error("更新过滤规则失败: %s", e)
                return False

    # ─── 事件管理 ──────────────────────────────────

    def save_event(self, monitor_id: int, event_type: str, payload: dict,
                   repo_name: str = "", actor: str = "", url: str = "") -> int:
        with self._write_lock:
            try:
                conn = self._get_conn()
                cur = conn.execute(
                    """INSERT INTO events
                       (monitor_id, event_type, payload, repo_name, actor, url)
                       VALUES (?,?,?,?,?,?)""",
                    (monitor_id, event_type, json.dumps(payload),
                     repo_name, actor, url),
                )
                conn.commit()
                # 清理过期历史
                self._cleanup_old_events()
                return cur.lastrowid
            except sqlite3.Error as e:
                log.error("保存事件失败: %s", e)
                return -1

    def get_events(self, monitor_id: int = None, limit: int = 200,
                   offset: int = 0) -> list[dict]:
        conn = self._get_conn()
        if monitor_id:
            rows = conn.execute(
                """SELECT e.*, m.target as monitor_target
                   FROM events e JOIN monitors m ON e.monitor_id=m.id
                   WHERE e.monitor_id=? ORDER BY e.received_at DESC LIMIT ? OFFSET ?""",
                (monitor_id, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT e.*, m.target as monitor_target
                   FROM events e JOIN monitors m ON e.monitor_id=m.id
                   ORDER BY e.received_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            if isinstance(item.get("payload"), str):
                item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result

    def get_events_since(self, since: datetime, monitor_id: int = None) -> list[dict]:
        """获取指定时间后的新事件 (用于简报生成)"""
        conn = self._get_conn()
        if monitor_id:
            rows = conn.execute(
                "SELECT * FROM events WHERE monitor_id=? AND received_at>=? ORDER BY received_at",
                (monitor_id, since.isoformat()),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE received_at>=? ORDER BY received_at",
                (since.isoformat(),),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_unread_events(self, last_read_id: int = 0) -> int:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM events WHERE id>?", (last_read_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    def _cleanup_old_events(self, max_days: int = 30):
        """清理超过保留天数的事件 (每 50 次插入才执行一次)"""
        if not hasattr(self, "_cleanup_counter"):
            self._cleanup_counter = 0
        self._cleanup_counter += 1
        if self._cleanup_counter % 50 != 0:
            return
        days = config.get("max_history_days", max_days)
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        conn = self._get_conn()
        deleted = conn.execute("DELETE FROM events WHERE received_at<?", (cutoff,)).rowcount
        if deleted > 0:
            log.info("清理了 %d 条过期事件", deleted)

    # ─── Trending 缓存 ─────────────────────────────

    def save_trending_cache(self, language: str, since: str,
                            repo_id: str, repo_full_name: str, data: dict):
        with self._write_lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    """INSERT OR REPLACE INTO trending_cache
                       (language, since, repo_id, repo_full_name, data, fetched_at)
                       VALUES (?,?,?,?,?, CURRENT_TIMESTAMP)""",
                    (language, since, repo_id, repo_full_name, json.dumps(data)),
                )
                conn.commit()
            except sqlite3.Error as e:
                log.error("保存 trending 缓存失败: %s", e)

    def get_trending_cache(self, language: str, since: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT * FROM trending_cache
               WHERE language=? AND since=? ORDER BY fetched_at DESC""",
            (language, since),
        ).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            if isinstance(item.get("data"), str):
                item["data"] = json.loads(item["data"])
            result.append(item)
        return result

    def clear_trending_cache(self, language: str = None, since: str = None):
        with self._write_lock:
            conn = self._get_conn()
            if language and since:
                conn.execute(
                    "DELETE FROM trending_cache WHERE language=? AND since=?",
                    (language, since),
                )
            elif language:
                conn.execute(
                    "DELETE FROM trending_cache WHERE language=?", (language,)
                )
            else:
                conn.execute("DELETE FROM trending_cache")
            conn.commit()

    # ─── Star 快照 ─────────────────────────────────

    def save_star_snapshot(self, repo_full_name: str, star_count: int):
        with self._write_lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO star_snapshots (repo_full_name, star_count) VALUES (?,?)",
                    (repo_full_name, star_count),
                )
                conn.commit()
            except sqlite3.Error as e:
                log.error("保存 star 快照失败: %s", e)

    def get_star_history(self, repo_full_name: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT star_count, recorded_at FROM star_snapshots
               WHERE repo_full_name=? ORDER BY recorded_at ASC""",
            (repo_full_name,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_latest_star(self, repo_full_name: str) -> Optional[int]:
        conn = self._get_conn()
        r = conn.execute(
            """SELECT star_count FROM star_snapshots
               WHERE repo_full_name=? ORDER BY recorded_at DESC LIMIT 1""",
            (repo_full_name,),
        ).fetchone()
        return r["star_count"] if r else None

    # ─── 收藏夹 ────────────────────────────────────

    def add_bookmark(self, repo_full_name: str, repo_url: str = "",
                     description: str = "", language: str = "",
                     stars: int = 0, note: str = "") -> bool:
        with self._write_lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    """INSERT OR IGNORE INTO bookmarks
                       (repo_full_name, repo_url, description, language, stars, note)
                       VALUES (?,?,?,?,?,?)""",
                    (repo_full_name, repo_url, description, language, stars, note),
                )
                conn.commit()
                return True
            except sqlite3.Error as e:
                log.error("添加收藏失败: %s", e)
                return False

    def remove_bookmark(self, repo_full_name: str) -> bool:
        with self._write_lock:
            try:
                conn = self._get_conn()
                conn.execute("DELETE FROM bookmarks WHERE repo_full_name=?", (repo_full_name,))
                conn.commit()
                return True
            except sqlite3.Error as e:
                log.error("删除收藏失败: %s", e)
                return False

    def get_bookmarks(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM bookmarks ORDER BY saved_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def is_bookmarked(self, repo_full_name: str) -> bool:
        conn = self._get_conn()
        r = conn.execute(
            "SELECT 1 FROM bookmarks WHERE repo_full_name=?", (repo_full_name,)
        ).fetchone()
        return r is not None

    # ─── 搜索历史 ──────────────────────────────────

    def add_search_history(self, query: str):
        with self._write_lock:
            try:
                conn = self._get_conn()
                conn.execute(
                    "INSERT INTO search_history (query) VALUES (?)", (query,)
                )
                conn.commit()
            except sqlite3.Error as e:
                log.error("保存搜索历史失败: %s", e)

    def get_search_history(self, limit: int = 20) -> list[str]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT query FROM search_history GROUP BY query ORDER BY MAX(searched_at) DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["query"] for r in rows]

    def clear_search_history(self):
        with self._write_lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM search_history")
            conn.commit()

    # ─── 配置管理 ──────────────────────────────────

    def get_config_value(self, key: str, default=None) -> Optional[str]:
        """读取 config 表 (用于持久化配置)"""
        # 优先使用 Config 类
        from src.common.config import config
        return config.get(key, default)

    # ─── 统计 ──────────────────────────────────────

    def get_stats(self) -> dict:
        conn = self._get_conn()
        monitor_count = conn.execute("SELECT COUNT(*) FROM monitors").fetchone()[0]
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        bookmark_count = conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
        return {
            "monitors": monitor_count,
            "events": event_count,
            "bookmarks": bookmark_count,
        }


# 全局单例
db = DatabaseManager()

"""
DevRadar 服务端核心 — TCP Socket 服务器
- 接受客户端连接
- 命令分发处理
- 心跳检测与自动重连
"""

import json
import socket
import threading
import time
from datetime import datetime
from queue import Queue
from typing import Optional

from src.common.config import config
from src.common.logger import get_logger
from src.common import protocol as proto
from src.server.db_manager import db
from src.server.github_api import api, GitHubAPIError

log = get_logger("server")


class DevRadarServer:
    """TCP Socket 服务端 — 单客户端设计 (本地进程通信)"""

    def __init__(self):
        self.host = config.get("socket_host", "127.0.0.1")
        self.port = config.get("socket_port", 9669)
        self.server_socket: Optional[socket.socket] = None
        self.client_socket: Optional[socket.socket] = None
        self.client_addr: Optional[tuple] = None
        self.running = False
        self._send_queue = Queue()
        self._lock = threading.Lock()

        # 回调注册 — 给其他模块用
        self.on_event_callback = None

    def start(self):
        """启动服务端 (阻塞线程)"""
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(1)
        self.server_socket.settimeout(2.0)
        log.info("服务端已启动: %s:%s", self.host, self.port)

        # 发送线程
        sender = threading.Thread(target=self._send_loop, daemon=True, name="server-sender")
        sender.start()

        while self.running:
            try:
                conn, addr = self.server_socket.accept()
                log.info("客户端已连接: %s:%s", *addr)
                with self._lock:
                    self.client_socket = conn
                    self.client_addr = addr

                # 处理客户端消息 (阻塞)
                self._handle_client(conn)
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as e:
                log.error("服务端异常: %s", e)

        self._cleanup()
        log.info("服务端已停止")

    def stop(self):
        """停止服务端"""
        self.running = False
        # 发送哨兵值, 让 _send_loop 退出
        self._send_queue.put(None)
        self._cleanup()
        log.info("服务端已停止")

    def _cleanup(self):
        """清理连接"""
        with self._lock:
            if self.client_socket:
                try:
                    self.client_socket.close()
                except OSError:
                    pass
                self.client_socket = None
            if self.server_socket:
                try:
                    self.server_socket.close()
                except OSError:
                    pass
                self.server_socket = None

    def send(self, data: bytes):
        """发送消息到客户端 (线程安全)"""
        self._send_queue.put(data)

    def _send_loop(self):
        """发送线程"""
        while self.running:
            data = self._send_queue.get()
            if data is None:
                break
            with self._lock:
                if self.client_socket:
                    try:
                        self.client_socket.sendall(data)
                    except (OSError, BrokenPipeError) as e:
                        log.warning("发送失败 (客户端可能已断开): %s", e)
                        self.client_socket = None

    def _handle_client(self, conn: socket.socket):
        """处理单个客户端连接的消息流"""
        buffer = ""
        conn.settimeout(60)

        while self.running:
            try:
                chunk = conn.recv(4096)
                if not chunk:
                    log.info("客户端已断开")
                    break
                buffer += chunk.decode("utf-8")
                # 按 \n 分割处理
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._process_message(line, conn)
            except socket.timeout:
                # 超时正常, 检查是否需要发送心跳响应
                self._send_heartbeat_if_needed(conn)
                continue
            except (OSError, ConnectionError) as e:
                log.warning("客户端连接异常: %s", e)
                break
            except Exception as e:
                log.error("消息处理异常: %s", e, exc_info=True)
                continue

        with self._lock:
            if self.client_socket == conn:
                self.client_socket = None
                self.client_addr = None

    def _send_heartbeat_if_needed(self, conn: socket.socket):
        """发送心跳响应"""
        # 当客户端发送心跳时, 回复心跳
        pass  # 心跳由 send 方法处理

    def _process_message(self, line: str, conn: socket.socket):
        """处理一条消息"""
        try:
            msg = proto.unpack(line)
        except json.JSONDecodeError as e:
            log.warning("消息解析失败: %s", e)
            return

        msg_type = msg.get("type", "")

        if msg_type == proto.TYPE_HEARTBEAT:
            self.send(proto.heartbeat())

        elif msg_type == proto.TYPE_COMMAND:
            self._handle_command(msg, conn)

        else:
            log.warning("未知消息类型: %s", msg_type)

    def _handle_command(self, msg: dict, conn: socket.socket):
        """处理命令消息"""
        action = msg.get("action", "")
        log.info("收到命令: %s", action)

        try:
            handler = getattr(self, f"_cmd_{action}", None)
            if handler:
                handler(msg, conn)
            else:
                self.send(proto.ack(action, False, error=f"未知命令: {action}"))
        except Exception as e:
            log.error("命令执行失败 %s: %s", action, e)
            self.send(proto.ack(action, False, error=str(e)))

    # ═══════════════════════════════════════
    # 命令处理
    # ═══════════════════════════════════════

    def _cmd_add_monitor(self, msg: dict, conn: socket.socket):
        """添加监控目标"""
        target = msg.get("target", "").strip()
        if not target:
            self.send(proto.ack("add_monitor", False, error="目标不能为空"))
            return

        # 判断类型: 包含 "/" 则是 repo, 否则 user
        mtype = "repo" if "/" in target else "user"

        # 验证目标存在
        try:
            if mtype == "repo":
                api.get_repo(target)
            else:
                api.get_user_events(target)  # 简单验证
        except GitHubAPIError as e:
            self.send(proto.ack("add_monitor", False, error=str(e)))
            return

        filters = msg.get("filters", {})
        mid = db.add_monitor(target, mtype, filters)
        if mid > 0:
            self.send(proto.ack("add_monitor", True, monitor_id=mid, target=target))
            log.info("监控已添加: %s (type=%s, id=%s)", target, mtype, mid)
        else:
            self.send(proto.ack("add_monitor", False, error="监控已存在或添加失败"))

    def _cmd_remove_monitor(self, msg: dict, conn: socket.socket):
        mid = msg.get("monitor_id")
        if not mid:
            self.send(proto.ack("remove_monitor", False, error="缺少 monitor_id"))
            return
        ok = db.remove_monitor(mid)
        self.send(proto.ack("remove_monitor", ok))

    def _cmd_list_monitors(self, msg: dict, conn: socket.socket):
        monitors = db.get_monitors()
        self.send(proto.ack("list_monitors", True, monitors=monitors))

    def _cmd_update_filters(self, msg: dict, conn: socket.socket):
        mid = msg.get("monitor_id")
        filters = msg.get("filters", {})
        if not mid:
            self.send(proto.ack("update_filters", False, error="缺少 monitor_id"))
            return
        ok = db.update_filters(mid, filters)
        self.send(proto.ack("update_filters", ok))

    def _cmd_search_repos(self, msg: dict, conn: socket.socket):
        """搜索仓库"""
        query = msg.get("query", "").strip()
        if not query:
            self.send(proto.ack("search_repos", False, error="搜索词不能为空"))
            return

        language = msg.get("language", "")
        stars_min = msg.get("stars_min", 0)
        stars_max = msg.get("stars_max", 0)
        page = msg.get("page", 1)

        try:
            result = api.search_repos(
                query, language=language,
                stars_min=stars_min, stars_max=stars_max,
                page=page,
            )
            items = []
            for r in result.get("items", []):
                items.append({
                    "full_name": r.get("full_name", ""),
                    "name": r.get("name", ""),
                    "description": r.get("description", "") or "",
                    "language": r.get("language") or "",
                    "stars": r.get("stargazers_count", 0),
                    "forks": r.get("forks_count", 0),
                    "url": r.get("html_url", ""),
                    "updated_at": r.get("updated_at", ""),
                    "owner": r.get("owner", {}).get("login", ""),
                    "topics": r.get("topics", []),
                })

            self.send(proto.search_result(
                query=query,
                data=items,
                rate_remaining=api.rate_limit.remaining,
            ))

            # 保存搜索历史
            db.add_search_history(query)

        except GitHubAPIError as e:
            self.send(proto.status("error", f"搜索失败: {e}"))

    def _cmd_fetch_trending(self, msg: dict, conn: socket.socket):
        """获取 Trending 数据"""
        language = msg.get("language", "") or "all"
        since = msg.get("since", "daily")

        # 尝试从缓存读取
        cached = db.get_trending_cache(language, since)
        if cached:
            data = [item["data"] for item in cached]
            self.send(proto.trending_data(language, since, data))
            return

        # 抓取
        from src.server.trending import fetch_trending
        try:
            data = fetch_trending(language, since)
            # 缓存结果
            for item in data:
                db.save_trending_cache(
                    language, since,
                    item["full_name"], item["full_name"], item,
                )
            self.send(proto.trending_data(language, since, data))
        except Exception as e:
            self.send(proto.status("error", f"获取 Trending 失败: {e}"))

    def _cmd_generate_report(self, msg: dict, conn: socket.socket):
        """生成简报 (委托给 report_generator)"""
        from src.server.report_generator import generate_report
        period = msg.get("period", "weekly")
        language = msg.get("language", config.get("default_language", "python"))
        try:
            content = generate_report(period=period, language=language)
            self.send(proto.report_result(period, content))
        except Exception as e:
            self.send(proto.status("error", f"生成简报失败: {e}"))

    def _cmd_get_insight(self, msg: dict, conn: socket.socket):
        """获取项目洞察数据"""
        from src.server.report_generator import get_insight_data
        repo = msg.get("repo", "")
        if not repo:
            self.send(proto.ack("get_insight", False, error="缺少 repo"))
            return
        try:
            insight = get_insight_data(repo)
            self.send(proto.ack("get_insight", True, **insight))
        except Exception as e:
            self.send(proto.ack("get_insight", False, error=str(e)))

    def _cmd_bookmark_add(self, msg: dict, conn: socket.socket):
        ok = db.add_bookmark(
            msg.get("repo_full_name", ""),
            repo_url=msg.get("url", ""),
            description=msg.get("description", ""),
            language=msg.get("language", ""),
            stars=msg.get("stars", 0),
        )
        self.send(proto.ack("bookmark_add", ok))

    def _cmd_bookmark_list(self, msg: dict, conn: socket.socket):
        bookmarks = db.get_bookmarks()
        self.send(proto.ack("bookmark_list", True, bookmarks=bookmarks))

    def _cmd_bookmark_remove(self, msg: dict, conn: socket.socket):
        repo = msg.get("repo_full_name", "")
        ok = db.remove_bookmark(repo)
        self.send(proto.ack("bookmark_remove", ok))

    def _cmd_search_history(self, msg: dict, conn: socket.socket):
        history = db.get_search_history()
        self.send(proto.ack("search_history", True, history=history))

    def _cmd_clear_history(self, msg: dict, conn: socket.socket):
        db.clear_search_history()
        self.send(proto.ack("clear_history", True))

    def _cmd_get_rate_limit(self, msg: dict, conn: socket.socket):
        info = api.get_rate_limit_info()
        self.send(proto.ack("get_rate_limit", True, **{
            "remaining": info.remaining,
            "limit": info.limit,
            "reset_at": str(info.reset_at) if info.reset_at else "",
        }))

    def _cmd_set_config(self, msg: dict, conn: socket.socket):
        key = msg.get("key", "")
        value = msg.get("value")
        if not key:
            self.send(proto.ack("set_config", False, error="缺少 key"))
            return
        config.set(key, value)
        self.send(proto.ack("set_config", True))

    def _cmd_get_config(self, msg: dict, conn: socket.socket):
        all_config = {k: v for k, v in config.data.items() if k != "github_token"}
        self.send(proto.ack("get_config", True, config=all_config))

"""
DevRadar GUI Socket 客户端
- 连接管理 / 自动重连 / 心跳
- 消息收发 / 信号通知 UI
"""

import json
import socket
import threading
import time
from queue import Queue, Empty
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal

from src.common.config import config
from src.common.logger import get_logger
from src.common import protocol as proto

log = get_logger("client")


class DevRadarClient(QObject):
    """Socket 客户端 — 通过信号与 GUI 通信"""

    # 信号
    connected = pyqtSignal()
    disconnected = pyqtSignal(str)  # reason
    message_received = pyqtSignal(str, dict)  # msg_type, payload
    status_changed = pyqtSignal(str, str)  # code, message
    error_occurred = pyqtSignal(str)  # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.host = config.get("socket_host", "127.0.0.1")
        self.port = config.get("socket_port", 9669)
        self.sock: Optional[socket.socket] = None
        self._running = False
        self._send_queue = Queue()
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0
        self._last_heartbeat = 0.0
        self._reader_thread: Optional[threading.Thread] = None
        self._sender_thread: Optional[threading.Thread] = None
        self._reconnect_thread: Optional[threading.Thread] = None

    # ─── 连接管理 ─────────────────────────────

    def start(self):
        """启动客户端 (开始连接)"""
        self._running = True
        self._reconnect_thread = threading.Thread(
            target=self._connect_loop, daemon=True, name="client-reconnector"
        )
        self._reconnect_thread.start()

    def stop(self):
        """停止客户端"""
        self._running = False
        self._disconnect()
        log.info("客户端已停止")

    def _connect_loop(self):
        """重连循环 — 断线后自动重连, 永不退出"""
        while self._running:
            delay = self._reconnect_delay
            try:
                self._connect()
                delay = self._reconnect_delay  # 成功后重置

                self._reader_thread = threading.Thread(
                    target=self._read_loop, daemon=True, name="client-reader"
                )
                self._reader_thread.start()
                self._sender_thread = threading.Thread(
                    target=self._send_loop, daemon=True, name="client-sender"
                )
                self._sender_thread.start()

                # 等待读取线程结束 (连接断开时自然退出)
                if self._reader_thread:
                    self._reader_thread.join()

                log.info("连接已断开, 准备重连...")
                self._disconnect()

            except (ConnectionRefusedError, OSError) as e:
                self.disconnected.emit(f"连接失败: {e}")
                log.warning("连接失败, %.1fs 后重试: %s", delay, e)
                self._wait_with_check(delay)
                delay = min(delay * 2, self._max_reconnect_delay)
            except Exception as e:
                log.error("连接异常: %s", e)
                self.error_occurred.emit(str(e))
                self._wait_with_check(5)

    def _connect(self):
        """建立 TCP 连接"""
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(60)
        self.connected.emit()
        self._last_heartbeat = time.time()
        log.info("已连接到服务端 %s:%s", self.host, self.port)

    def _disconnect(self):
        """断开连接"""
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _wait_with_check(self, seconds: float):
        """等待同时检查是否需要停止"""
        step = 0.5
        waited = 0
        while waited < seconds and self._running:
            time.sleep(step)
            waited += step

    # ─── 消息收发 ─────────────────────────────

    def send_command(self, action: str, **params):
        """发送命令到服务端 (线程安全)"""
        self._send_queue.put(proto.command(action, **params))

    def send_raw(self, data: bytes):
        """发送原始消息"""
        self._send_queue.put(data)

    def _read_loop(self):
        """读取线程: 不断接收服务端消息"""
        buffer = ""
        while self._running and self.sock:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    log.info("服务端连接断开")
                    self.disconnected.emit("服务端连接断开")
                    self._disconnect()
                    break

                buffer += chunk.decode("utf-8")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    self._handle_message(line)

            except socket.timeout:
                # 定时发送心跳
                self._send_heartbeat()
                continue
            except (OSError, ConnectionError) as e:
                if self._running:
                    log.warning("读取异常: %s", e)
                    self.disconnected.emit(str(e))
                    self._disconnect()
                break
            except Exception as e:
                log.error("消息处理异常: %s", e, exc_info=True)
                continue

    def _send_loop(self):
        """发送线程: 从队列取出并发送"""
        while self._running:
            try:
                data = self._send_queue.get(timeout=1)
                if self.sock:
                    try:
                        self.sock.sendall(data)
                    except OSError as e:
                        log.warning("发送失败: %s", e)
                        self._send_queue.put(data)  # 放回队列
                        break
            except Empty:
                continue

    def _send_heartbeat(self):
        """发送心跳"""
        now = time.time()
        if now - self._last_heartbeat > 30:
            self._last_heartbeat = now
            self.send_raw(proto.heartbeat())

    def _handle_message(self, line: str):
        """分发收到的消息到信号"""
        try:
            msg = proto.unpack(line)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")

        if msg_type == proto.TYPE_HEARTBEAT:
            self._last_heartbeat = time.time()
            return

        if msg_type == proto.TYPE_STATUS:
            self.status_changed.emit(msg.get("code", ""), msg.get("message", ""))

        elif msg_type == proto.TYPE_SEARCH_RESULT:
            self.message_received.emit(proto.TYPE_SEARCH_RESULT, msg)

        elif msg_type == proto.TYPE_TRENDING_DATA:
            self.message_received.emit(proto.TYPE_TRENDING_DATA, msg)

        elif msg_type == proto.TYPE_NEW_EVENT:
            self.message_received.emit(proto.TYPE_NEW_EVENT, msg)

        elif msg_type == proto.TYPE_REPORT_RESULT:
            self.message_received.emit(proto.TYPE_REPORT_RESULT, msg)

        elif msg_type == proto.TYPE_ACK:
            self.message_received.emit(proto.TYPE_ACK, msg)

        else:
            self.message_received.emit(msg_type, msg)

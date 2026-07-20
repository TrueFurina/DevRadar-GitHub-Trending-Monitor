"""
DevRadar Socket 通信协议
所有消息为 JSON 对象，以 \\n 结尾

消息类型 (type):
  search_result  — 搜索结果
  trending_data  — 趋势数据
  new_event      — 新事件推送
  command        — 客户端指令
  ack            — 服务端应答
  status         — 状态信息
  heartbeat      — 心跳
  report_result  — 简报生成结果
"""

import json
from datetime import datetime, date


class DevRadarEncoder(json.JSONEncoder):
    """处理 datetime 等非标准 JSON 类型"""
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

# ─── 消息类型常量 ───
TYPE_SEARCH_RESULT  = "search_result"
TYPE_TRENDING_DATA  = "trending_data"
TYPE_NEW_EVENT      = "new_event"
TYPE_COMMAND        = "command"
TYPE_ACK            = "ack"
TYPE_STATUS         = "status"
TYPE_HEARTBEAT      = "heartbeat"
TYPE_REPORT_RESULT  = "report_result"

# ─── 动作常量 (command.action) ───
ACTION_ADD_MONITOR      = "add_monitor"
ACTION_REMOVE_MONITOR   = "remove_monitor"
ACTION_LIST_MONITORS    = "list_monitors"
ACTION_UPDATE_FILTERS   = "update_filters"
ACTION_GENERATE_REPORT  = "generate_report"
ACTION_GET_INSIGHT      = "get_insight"
ACTION_SET_CONFIG       = "set_config"
ACTION_GET_CONFIG       = "get_config"
ACTION_GET_RATE_LIMIT   = "get_rate_limit"
ACTION_FETCH_TRENDING   = "fetch_trending"
ACTION_SEARCH_REPOS     = "search_repos"
ACTION_BOOKMARK_ADD     = "bookmark_add"
ACTION_BOOKMARK_LIST    = "bookmark_list"
ACTION_BOOKMARK_REMOVE  = "bookmark_remove"
ACTION_SEARCH_HISTORY   = "search_history"
ACTION_CLEAR_HISTORY    = "clear_history"

# ─── 状态码 ───
STATUS_OK         = "ok"
STATUS_RATE_LIMIT = "rate_limit"
STATUS_ERROR      = "error"
STATUS_WARNING    = "warning"
STATUS_INFO       = "info"


def pack(msg_type: str, **fields) -> bytes:
    """打包为带换行符的 JSON 字节串 (支持 datetime 自动序列化)"""
    msg = {"type": msg_type}
    msg.update(fields)
    return (json.dumps(msg, ensure_ascii=False, cls=DevRadarEncoder) + "\n").encode("utf-8")


def unpack(raw: str) -> dict:
    """解析一行 JSON 文本"""
    return json.loads(raw.strip())


# ─── 快捷构造 ───

def heartbeat() -> bytes:
    return pack(TYPE_HEARTBEAT)


def status(code: str, message: str) -> bytes:
    return pack(TYPE_STATUS, code=code, message=message)


def ack(action: str, success: bool, **extra) -> bytes:
    return pack(TYPE_ACK, action=action, success=success, **extra)


def command(action: str, **params) -> bytes:
    return pack(TYPE_COMMAND, action=action, **params)


def new_event(monitor_id: int, event: dict) -> bytes:
    return pack(TYPE_NEW_EVENT, monitor_id=monitor_id, event=event)


def search_result(query: str, data: list, rate_remaining: int) -> bytes:
    return pack(TYPE_SEARCH_RESULT, query=query, data=data,
                rate_remaining=rate_remaining)


def trending_data(language: str, since: str, data: list) -> bytes:
    return pack(TYPE_TRENDING_DATA, language=language, since=since, data=data)


def report_result(period: str, content: str) -> bytes:
    return pack(TYPE_REPORT_RESULT, period=period, content=content)

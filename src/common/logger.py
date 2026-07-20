"""
DevRadar 统一日志模块
- 文件轮转 (5MB × 3)
- 控制台输出
- 统一格式: 时间 | 级别 | 模块 | 消息
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

_LOG_INSTANCES: dict[str, logging.Logger] = {}


def get_logger(name: str = "DevRadar",
               log_file: str = "data/devradar.log",
               level: int = logging.DEBUG) -> logging.Logger:
    """获取/创建命名的日志器"""
    if name in _LOG_INSTANCES:
        return _LOG_INSTANCES[name]

    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 防止重复 handler
    if logger.handlers:
        _LOG_INSTANCES[name] = logger
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件轮转 handler
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # 控制台 handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _LOG_INSTANCES[name] = logger
    return logger


# 默认日志器 — 各模块直接 import log 使用
log = get_logger()

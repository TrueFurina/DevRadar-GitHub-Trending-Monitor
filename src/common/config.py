"""
DevRadar 配置管理
读取顺序: 环境变量 GITHUB_TOKEN > config.json > 默认值
"""

import os
import json
from pathlib import Path

DEFAULT_CONFIG = {
    "github_token": "",
    "poll_interval_seconds": 300,
    "trending_refresh_seconds": 600,
    "snapshot_interval_hours": 6,
    "report_period": "weekly",
    "default_language": "python",
    "notification_enabled": True,
    "max_history_days": 30,
    "socket_host": "127.0.0.1",
    "socket_port": 9669,
    "trending_source": "html",          # "html" | "api"
    "github_api_base": "https://api.github.com",
    "trending_api_fallback": "https://gh-trending-api.herokuapp.com",
}


class Config:
    """全局配置管理器 — 单例模式"""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_path: str = "data/config.json"):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.config_path = Path(config_path)
        self.data = DEFAULT_CONFIG.copy()
        self._load()

    def _load(self):
        """按优先级加载配置: 文件 → 环境变量"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    file_data = json.load(f)
                self.data.update(file_data)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Config] 配置文件读取失败: {e}")

        env_token = os.getenv("GITHUB_TOKEN")
        if env_token:
            self.data["github_token"] = env_token

    def save(self):
        """持久化到文件 (不保存 token 到文件)"""
        save_data = {k: v for k, v in self.data.items() if k != "github_token"}
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value):
        self.data[key] = value
        # 自动保存关键变更
        if key in ("poll_interval_seconds", "default_language",
                    "report_period", "notification_enabled"):
            self.save()

    @property
    def token(self) -> str:
        return self.data.get("github_token") or ""

    @token.setter
    def token(self, value: str):
        self.data["github_token"] = value

    def has_token(self) -> bool:
        return bool(self.token)


# 全局单例
config = Config()

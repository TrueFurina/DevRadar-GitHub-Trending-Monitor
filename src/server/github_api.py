"""
GitHub REST API 封装
- 认证、限流感知、指数退避重试
- 所有方法在子线程调用, 不阻塞 GUI
"""

import time
import hashlib
from datetime import datetime
from typing import Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.common.config import config
from src.common.logger import get_logger

log = get_logger("github_api")

BASE_URL = "https://api.github.com"
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3
CACHE_TTL = 60  # 相同请求的缓存秒数


class GitHubAPIError(Exception):
    """GitHub API 调用异常"""
    pass


class RateLimitInfo:
    """API 限流信息"""

    def __init__(self):
        self.remaining: int = 60
        self.limit: int = 60
        self.reset_at: Optional[datetime] = None
        self.used: int = 0

    def update_from_headers(self, headers: dict):
        try:
            self.limit = int(headers.get("X-RateLimit-Limit", 60))
            self.remaining = int(headers.get("X-RateLimit-Remaining", 0))
            self.used = int(headers.get("X-RateLimit-Used", 0))
            reset_ts = int(headers.get("X-RateLimit-Reset", 0))
            if reset_ts:
                self.reset_at = datetime.fromtimestamp(reset_ts)
        except (ValueError, TypeError):
            pass

    def __str__(self) -> str:
        reset_info = f" 重置于 {self.reset_at}" if self.reset_at else ""
        return f"API 限流: {self.remaining}/{self.limit} 剩余{reset_info}"

    def is_nearly_exhausted(self) -> bool:
        return self.remaining < 20


class GitHubAPI:
    """GitHub REST API 客户端"""

    def __init__(self):
        self.rate_limit = RateLimitInfo()
        self._session = None
        self._current_token = None
        self._request_cache: dict[str, tuple[float, dict]] = {}
        self._rebuild_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=MAX_RETRIES,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=5, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "DevRadar/1.0",
        })
        return session

    def _rebuild_session(self):
        """重建 session (token 变化时调用)"""
        self._current_token = config.token
        self._session = self._build_session()
        if self._current_token:
            self._session.headers["Authorization"] = f"token {self._current_token}"
        log.info("API Session 已重建 (token=%s...)", self._current_token[:8] if self._current_token else "none")

    def _cache_key(self, url: str, params: dict = None) -> str:
        raw = url + str(sorted((params or {}).items()))
        return hashlib.md5(raw.encode()).hexdigest()

    def _get_cached(self, key: str) -> Optional[dict]:
        if key in self._request_cache:
            ts, data = self._request_cache[key]
            if time.time() - ts < CACHE_TTL:
                return data
            del self._request_cache[key]
        return None

    def _set_cache(self, key: str, data: dict):
        self._request_cache[key] = (time.time(), data)

    def _request(self, method: str, path: str, params: dict = None,
                 use_cache: bool = True, **kwargs) -> dict:
        url = f"{BASE_URL}{path}" if path.startswith("/") else path

        # 检查 token 是否变化, 变化则重建 session
        current_token = config.token
        if current_token != self._current_token:
            self._rebuild_session()

        cache_key = None
        if use_cache and method.upper() == "GET":
            cache_key = self._cache_key(url, params)
            cached = self._get_cached(cache_key)
            if cached:
                return cached

        try:
            resp = self._session.request(
                method, url, params=params, timeout=REQUEST_TIMEOUT, **kwargs
            )
            self.rate_limit.update_from_headers(resp.headers)

            log.debug("%s %s → %s (剩余配额: %s)",
                      method, url, resp.status_code, self.rate_limit.remaining)

            if resp.status_code == 204:
                result = {}
            elif resp.status_code == 404:
                raise GitHubAPIError(f"资源不存在: {path}")
            elif resp.status_code == 403:
                raise GitHubAPIError(f"权限不足或限流: {self.rate_limit}")
            elif resp.status_code == 401:
                raise GitHubAPIError("Token 无效或未提供, 请检查 GITHUB_TOKEN")
            elif resp.status_code == 422:
                raise GitHubAPIError(f"参数错误: {resp.json().get('message', '')}")
            else:
                resp.raise_for_status()
                result = resp.json()

            if cache_key:
                self._set_cache(cache_key, result)
            return result

        except requests.exceptions.Timeout:
            raise GitHubAPIError(f"请求超时 ({REQUEST_TIMEOUT}s): {path}")
        except requests.exceptions.ConnectionError:
            raise GitHubAPIError(f"网络连接失败: {path}")
        except requests.exceptions.RequestException as e:
            raise GitHubAPIError(f"请求异常: {e}")

    def _paginate(self, path: str, params: dict = None,
                  max_pages: int = 1) -> list[dict]:
        """分页获取全部结果"""
        results = []
        params = params or {}
        params.setdefault("per_page", 30)

        for page in range(1, max_pages + 1):
            params["page"] = page
            try:
                data = self._request("GET", path, params=params, use_cache=False)
                if not data:
                    break
                results.extend(data if isinstance(data, list) else [data])
            except GitHubAPIError:
                break
        return results

    # ═══════════════════════════════════════════
    # 公共 API
    # ═══════════════════════════════════════════

    def search_repos(self, query: str, language: str = "",
                     stars_min: int = 0, stars_max: int = 0,
                     sort: str = "stars", order: str = "desc",
                     page: int = 1, per_page: int = 30) -> dict:
        """
        搜索仓库
        返回: {"total_count": int, "items": [repo_dict, ...]}
        """
        q_parts = [f"{query} in:name"]
        if language:
            q_parts.append(f"language:{language}")
        if stars_min > 0:
            q_part = f"stars:>={stars_min}"
            if stars_max > 0:
                q_part = f"stars:{stars_min}..{stars_max}"
            q_parts.append(q_part)

        params = {
            "q": " ".join(q_parts),
            "sort": sort,
            "order": order,
            "page": page,
            "per_page": min(per_page, 100),
        }
        return self._request("GET", "/search/repositories", params=params)

    def get_repo(self, full_name: str) -> dict:
        """获取单个仓库信息"""
        return self._request("GET", f"/repos/{full_name}")

    def get_user_events(self, username: str, page: int = 1,
                        per_page: int = 30) -> list[dict]:
        """获取用户公开事件"""
        return self._request(
            "GET", f"/users/{username}/events",
            params={"page": page, "per_page": per_page},
            use_cache=False,
        )

    def get_repo_events(self, full_name: str, page: int = 1,
                        per_page: int = 30) -> list[dict]:
        """获取仓库事件"""
        return self._request(
            "GET", f"/repos/{full_name}/events",
            params={"page": page, "per_page": per_page},
            use_cache=False,
        )

    def get_user_repos(self, username: str, sort: str = "updated",
                       per_page: int = 50) -> list[dict]:
        """获取用户仓库列表"""
        return self._paginate(
            f"/users/{username}/repos",
            params={"sort": sort, "type": "owner"},
            max_pages=2,
        )

    def get_user_starred(self, username: str, per_page: int = 50) -> list[dict]:
        """获取用户 Starred 仓库"""
        return self._paginate(
            f"/users/{username}/starred",
            params={"per_page": per_page},
            max_pages=2,
        )

    def get_repo_contributors(self, full_name: str) -> list[dict]:
        """获取仓库贡献者"""
        return self._paginate(f"/repos/{full_name}/contributors", max_pages=1)

    def get_repo_issues(self, full_name: str, state: str = "open",
                        per_page: int = 30) -> list[dict]:
        """获取仓库 Issues"""
        return self._request(
            "GET", f"/repos/{full_name}/issues",
            params={"state": state, "per_page": per_page},
            use_cache=False,
        )

    def check_rate_limit(self) -> dict:
        """单独检查限流"""
        return self._request("GET", "/rate_limit", use_cache=False)

    def validate_token(self) -> bool:
        """验证 Token 是否有效"""
        try:
            self._request("GET", "/user", use_cache=False)
            return True
        except GitHubAPIError:
            return False

    def get_rate_limit_info(self) -> RateLimitInfo:
        """获取当前限流状态"""
        try:
            self.check_rate_limit()
        except GitHubAPIError:
            pass
        return self.rate_limit


# 全局实例
api = GitHubAPI()

"""
GitHub Trending 数据获取
双模式: HTML 爬取 (主) → API 备用 (自动切换)
所有方法可安全地在子线程调用
"""

import re
import json
import time
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

from src.common.config import config
from src.common.logger import get_logger

log = get_logger("trending")

TRENDING_URL = "https://github.com/trending"
TRENDING_API_FALLBACK = "https://gh-trending-api.herokuapp.com"
REQUEST_TIMEOUT = 12
LANGUAGES = ["", "python", "java", "go", "javascript", "typescript",
             "rust", "c", "cpp", "ruby", "php", "swift", "kotlin",
             "scala", "dart", "elixir", "haskell", "lua"]
SINCE_OPTIONS = ["daily", "weekly", "monthly"]

# 语言配色 (用于标签显示)
LANG_COLORS = {
    "python": "#3572A5", "java": "#B07219", "go": "#00ADD8",
    "javascript": "#F7DF1E", "typescript": "#3178C6", "rust": "#DEA584",
    "c": "#555555", "cpp": "#F34B7D", "ruby": "#701516",
    "php": "#4F5D95", "swift": "#FFAC45", "kotlin": "#F18E33",
    "scala": "#C22D40", "dart": "#00B4AB", "elixir": "#6E4A7E",
    "haskell": "#5D4F85", "lua": "#000080",
}


def _parse_trending_html(html: str) -> list[dict]:
    """从 HTML 解析 Trending 列表"""
    soup = BeautifulSoup(html, "html.parser")
    articles = soup.select("article.Box-row")
    results = []

    for article in articles:
        try:
            # 仓库名
            h2 = article.select_one("h2")
            if not h2:
                continue
            repo_link = h2.select_one("a")
            if not repo_link:
                continue
            full_name = repo_link.get("href", "").strip("/")
            repo_url = f"https://github.com/{full_name}"

            # 描述
            desc_tag = article.select_one("p")
            description = desc_tag.text.strip() if desc_tag else ""

            # 语言
            lang_tag = article.select_one("[itemprop='programmingLanguage']")
            language = lang_tag.text.strip() if lang_tag else ""

            # Star / Fork 数
            stars_tag = article.select_one("a[href$='/stargazers']")
            forks_tag = article.select_one("a[href$='/forks']")

            stars = 0
            forks = 0
            if stars_tag:
                stars_text = stars_tag.text.strip().replace(",", "")
                stars = int(re.search(r"\d+", stars_text).group()) if re.search(r"\d+", stars_text) else 0
            if forks_tag:
                forks_text = forks_tag.text.strip().replace(",", "")
                forks = int(re.search(r"\d+", forks_text).group()) if re.search(r"\d+", forks_text) else 0

            # 今日新增 Star
            delta_tag = article.select_one(".float-sm-right")
            daily_stars = 0
            if delta_tag:
                delta_text = delta_tag.text.strip()
                match = re.search(r"(\d[\d,]*)", delta_text)
                if match:
                    daily_stars = int(match.group(1).replace(",", ""))

            # 内置 Stars 标签（有些仓库不显示数字）
            built_by = article.select_one(".f6 .Link--secondary")
            built_by_text = built_by.text.strip() if built_by else ""

            results.append({
                "full_name": full_name,
                "name": full_name.split("/")[-1] if "/" in full_name else full_name,
                "url": repo_url,
                "description": description,
                "language": language,
                "stars": stars,
                "forks": forks,
                "daily_stars": daily_stars,
                "built_by": built_by_text,
            })
        except Exception as e:
            log.warning("解析 Trending 条目失败: %s", e)
            continue

    return results


def _fetch_trending_api(language: str = "", since: str = "daily") -> list[dict]:
    """备用方案: 通过非官方 API 获取"""
    lang_part = f"/{language}" if language else ""
    url = f"{TRENDING_API_FALLBACK}/repositories{lang_part}?since={since}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # 标准化格式
        results = []
        for item in data:
            results.append({
                "full_name": item.get("fullname", ""),
                "name": item.get("name", ""),
                "url": item.get("url", ""),
                "description": item.get("description", ""),
                "language": item.get("language", ""),
                "stars": item.get("stars", 0),
                "forks": item.get("forks", 0),
                "daily_stars": item.get("currentPeriodStars", 0),
                "built_by": "",
            })
        log.info("备用 API 获取 Trending 成功: %s/%s", lang_part.strip("/"), since)
        return results
    except Exception as e:
        log.error("备用 API 获取 Trending 失败: %s", e)
        raise


def fetch_trending(language: str = "", since: str = "daily") -> list[dict]:
    """
    获取 GitHub Trending 数据
    主方案: 解析 HTML → 失败时自动切 API 备用
    返回标准化字典列表
    """
    if not language:
        language = "all"
    if since not in SINCE_OPTIONS:
        since = "daily"

    # 标准化语言: "all" 表示全部语言, 对应空参数
    api_lang = language if language != "all" else ""
    html_lang = language if language != "all" else ""

    lang_part = f"/{html_lang}" if html_lang else ""
    url = f"{TRENDING_URL}{lang_part}?since={since}"

    source = config.get("trending_source", "html")

    # 如果配置指定用 API, 直接调 API
    if source == "api":
        return _fetch_trending_api(api_lang, since)

    # 主方案: HTML 爬取
    try:
        log.info("正在爬取 Trending: %s", url)
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": "DevRadar/1.0"},
        )
        resp.raise_for_status()

        results = _parse_trending_html(resp.text)

        # 验证结果: 如果为空, 可能是页面结构变了, 自动切换 API
        if not results:
            log.warning("HTML 解析结果为空, 自动切换备用 API")
            results = _fetch_trending_api(api_lang, since)

        log.info("Trending 获取完成: %s/%s → %d 条", lang_part.strip("/") or "all", since, len(results))
        return results

    except requests.exceptions.Timeout:
        log.warning("Trending 页面超时, 切换备用 API")
        return _fetch_trending_api(api_lang, since)
    except requests.exceptions.RequestException as e:
        log.warning("Trending 页面请求失败 (%s), 切换备用 API", e)
        return _fetch_trending_api(api_lang, since)
    except Exception as e:
        log.error("Trending 获取异常: %s", e, exc_info=True)
        # 最后一次尝试
        try:
            return _fetch_trending_api(api_lang, since)
        except Exception:
            return []


def get_language_color(language: str) -> str:
    """获取语言对应的背景色"""
    return LANG_COLORS.get(language.lower(), "#666666")

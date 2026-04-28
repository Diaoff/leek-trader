from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.news import NewsBriefResponse, NewsFeedResponse, NewsItemRead

logger = logging.getLogger(__name__)


class NewsProvider:
    xuan_gu_bao_endpoint = "https://baoer-api.xuangubao.com.cn/api/v6/message/newsflash"
    jiu_yan_endpoint = "https://app.jiuyangongshe.com/jystock-app/api/v2/article/search"
    jiu_yan_token_page = "https://hm.baidu.com/hm.js?58aa18061df7855800f2a1b32d6da7f4"
    xueqiu_timeline_endpoint = "https://xueqiu.com/v4/statuses/user_timeline.json"

    def fetch_market_news(self, limit: int = 12) -> list[str]:
        try:
            return [self._format_ai_item(item) for item in self.fetch_market_news_items(limit=limit)]
        except Exception as error:
            logger.warning("XuanGuBao news request failed: %s", error)
            return []

    def fetch_discussions(self, keyword: str, limit: int = 8) -> list[str]:
        try:
            return [self._format_ai_item(item, include_author=True) for item in self.fetch_discussion_items(keyword, limit=limit)]
        except Exception as error:
            logger.warning("JiuYanGongShe discussion request failed for keyword=%s: %s", keyword, error)
            return []

    def get_market_feed(self, limit: int = 20) -> NewsFeedResponse:
        try:
            return NewsFeedResponse(items=self.fetch_market_news_items(limit=limit), errors=[])
        except Exception as error:
            logger.warning("XuanGuBao news request failed: %s", error)
            return NewsFeedResponse(items=[], errors=["选股宝快讯获取失败"])

    def get_discussion_feed(self, keyword: str, limit: int = 10) -> NewsFeedResponse:
        try:
            return NewsFeedResponse(items=self.fetch_discussion_items(keyword, limit=limit), errors=[])
        except Exception as error:
            logger.warning("JiuYanGongShe discussion request failed for keyword=%s: %s", keyword, error)
            return NewsFeedResponse(items=[], errors=["九研文章获取失败"])

    def get_xueqiu_feed(self, limit: int = 20) -> NewsFeedResponse:
        user_ids = settings.xueqiu_user_id_list
        if not user_ids:
            return NewsFeedResponse(items=[], errors=["雪球未配置"])
        items: list[NewsItemRead] = []
        errors: list[str] = []
        per_user_limit = max(1, min(limit, (limit + len(user_ids) - 1) // len(user_ids)))
        for user_id in user_ids:
            try:
                items.extend(self.fetch_xueqiu_user_items(user_id, limit=per_user_limit))
            except Exception as error:
                logger.warning("Xueqiu timeline request failed for user_id=%s: %s", user_id, error)
                errors.append(f"雪球用户 {user_id} 动态获取失败")
        items.sort(key=lambda item: item.published_at or datetime.min, reverse=True)
        return NewsFeedResponse(items=items[:limit], errors=errors)

    def get_brief(self, keyword: str, limit: int = 10) -> NewsBriefResponse:
        errors: list[str] = []
        market = self.get_market_feed(limit=limit)
        discussions = self.get_discussion_feed(keyword, limit=limit)
        xueqiu = self.get_xueqiu_feed(limit=limit)
        errors.extend(market.errors)
        errors.extend(discussions.errors)
        errors.extend(xueqiu.errors)
        return NewsBriefResponse(
            market=market.items,
            discussions=discussions.items,
            xueqiu=xueqiu.items,
            errors=errors,
        )

    def fetch_market_news_items(self, limit: int = 12) -> list[NewsItemRead]:
        with httpx.Client(timeout=6.0, headers=self._browser_headers("https://xuangubao.com.cn/")) as client:
            response = client.get(self.xuan_gu_bao_endpoint, params={"limit": limit})
            response.raise_for_status()
            payload = response.json()
        return self._parse_xuan_gu_bao_items(payload, limit=limit)

    def fetch_discussion_items(self, keyword: str, limit: int = 8) -> list[NewsItemRead]:
        clean_keyword = keyword.strip()
        if not clean_keyword:
            return []
        token = self._fetch_jiu_yan_token()
        with httpx.Client(timeout=8.0, headers=self._jiu_yan_headers(token)) as client:
            response = client.post(
                self.jiu_yan_endpoint,
                json={"keyword": clean_keyword, "type": "all", "limit": limit, "start": 0},
            )
            response.raise_for_status()
            payload = response.json()
        return self._parse_jiu_yan_items(payload, keyword=clean_keyword, limit=limit)

    def fetch_xueqiu_user_items(self, user_id: str, limit: int = 20) -> list[NewsItemRead]:
        headers = self._browser_headers("https://xueqiu.com/")
        headers.update({"Accept": "application/json, text/plain, */*"})
        if settings.xueqiu_cookie:
            headers["Cookie"] = settings.xueqiu_cookie
        with httpx.Client(timeout=8.0, headers=headers) as client:
            response = client.get(self.xueqiu_timeline_endpoint, params={"user_id": user_id, "page": 1, "count": limit})
            response.raise_for_status()
            payload = response.json()
        return self._parse_xueqiu_items(payload, user_id=user_id, limit=limit)

    def _fetch_jiu_yan_token(self) -> str:
        response = httpx.get(
            self.jiu_yan_token_page,
            timeout=5.0,
            headers=self._browser_headers("https://www.jiuyangongshe.com/"),
        )
        return response.headers.get("etag", "").strip('"')

    @staticmethod
    def _browser_headers(referer: str) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Referer": referer,
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        }

    def _jiu_yan_headers(self, token: str) -> dict[str, str]:
        headers = self._browser_headers("https://www.jiuyangongshe.com/")
        headers.update({"Content-Type": "application/json;charset=UTF-8", "Origin": "https://www.jiuyangongshe.com"})
        if token:
            headers["Token"] = token
        return headers

    def _parse_xuan_gu_bao_items(self, payload: dict[str, Any], *, limit: int) -> list[NewsItemRead]:
        rows = self._extract_first_list(payload, keys=("messages", "items", "list", "data"))
        result: list[NewsItemRead] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = self._first_text(row, "title", "content", "summary", "description")
            if not title:
                continue
            published_at = self._parse_timestamp(row.get("created_at") or row.get("time") or row.get("updated_at"))
            result.append(
                NewsItemRead(
                    id=self._stable_id("xuangubao", row, title),
                    source="xuangubao",
                    title=title,
                    summary=self._first_text(row, "summary", "description", "content"),
                    published_at=published_at,
                    url=self._first_text(row, "url", "link", "share_url"),
                )
            )
            if len(result) >= limit:
                break
        return result

    def _parse_jiu_yan_items(self, payload: dict[str, Any], *, keyword: str, limit: int) -> list[NewsItemRead]:
        rows = self._extract_first_list(payload, keys=("list", "items", "articles", "data"))
        result: list[NewsItemRead] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = self._first_text(row, "title", "content", "summary", "description")
            if not title:
                continue
            result.append(
                NewsItemRead(
                    id=self._stable_id("jiuyangongshe", row, title),
                    source="jiuyangongshe",
                    title=title,
                    summary=self._first_text(row, "summary", "description", "content"),
                    published_at=self._parse_timestamp(row.get("created_at") or row.get("ctime") or row.get("time")),
                    author=self._first_text(row, "source", "author", "username", "user_name"),
                    url=self._first_text(row, "url", "link", "share_url"),
                    symbol_keyword=keyword,
                )
            )
            if len(result) >= limit:
                break
        return result

    def _parse_xueqiu_items(self, payload: dict[str, Any], *, user_id: str, limit: int) -> list[NewsItemRead]:
        rows = self._extract_first_list(payload, keys=("statuses", "list", "items", "data"))
        result: list[NewsItemRead] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = self._first_text(row, "title", "description", "text", "content")
            if not title:
                continue
            user = row.get("user") if isinstance(row.get("user"), dict) else {}
            author = self._first_text(user, "screen_name", "name") or self._first_text(row, "screen_name", "author") or user_id
            url = self._first_text(row, "target", "url", "link")
            if url.startswith("/"):
                url = f"https://xueqiu.com{url}"
            result.append(
                NewsItemRead(
                    id=self._stable_id("xueqiu", row, title),
                    source="xueqiu",
                    title=self._strip_html(title),
                    summary=self._strip_html(self._first_text(row, "description", "text", "content")),
                    published_at=self._parse_timestamp(row.get("created_at") or row.get("time") or row.get("createdAt")),
                    author=author,
                    url=url,
                )
            )
            if len(result) >= limit:
                break
        return result

    def _extract_first_list(self, value: Any, *, keys: tuple[str, ...]) -> list[Any]:
        if isinstance(value, list):
            return value
        if not isinstance(value, dict):
            return []
        for key in keys:
            child = value.get(key)
            if isinstance(child, list):
                return child
            nested = self._extract_first_list(child, keys=keys)
            if nested:
                return nested
        return []

    @staticmethod
    def _first_text(row: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = row.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text.replace("\n", " ")
        return ""

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            timestamp = float(value)
        except (TypeError, ValueError):
            text = str(value).strip()
            for candidate in (text, text[:19], text[:16]):
                try:
                    return datetime.fromisoformat(candidate.replace("Z", "+00:00"))
                except ValueError:
                    continue
            return None
        if timestamp > 100000000000:
            timestamp /= 1000
        try:
            return datetime.fromtimestamp(timestamp)
        except (OSError, ValueError):
            return None

    @staticmethod
    def _format_ai_item(item: NewsItemRead, *, include_author: bool = False) -> str:
        published_at = item.published_at.strftime("%m-%d %H:%M") if item.published_at else ""
        prefix_parts = [published_at]
        if include_author and item.author:
            prefix_parts.append(item.author)
        prefix = " · ".join(part for part in prefix_parts if part)
        return f"{prefix}：{item.title}" if prefix else item.title

    @staticmethod
    def _stable_id(source: str, row: dict[str, Any], title: str) -> str:
        raw = row.get("id") or row.get("news_id") or row.get("article_id") or row.get("status_id") or title
        digest = hashlib.sha1(f"{source}:{raw}".encode("utf-8")).hexdigest()[:16]
        return f"{source}-{digest}"

    @staticmethod
    def _strip_html(value: str) -> str:
        return value.replace("<p>", "").replace("</p>", "").replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ")

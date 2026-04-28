from __future__ import annotations

import importlib
from typing import Any

import pytest


class FakeResponse:
    def __init__(self, payload: dict[str, Any], headers: dict[str, str] | None = None, status_code: int = 200) -> None:
        self.payload = payload
        self.headers = headers or {}
        self.status_code = status_code

    def json(self) -> dict[str, Any]:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    calls: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = []
    responses: list[FakeResponse] = []

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url: str, params: dict[str, Any] | None = None) -> FakeResponse:
        self.calls.append(("GET", params, None))
        return self.responses.pop(0)

    def post(self, url: str, json: dict[str, Any] | None = None) -> FakeResponse:
        self.calls.append(("POST", None, json))
        return self.responses.pop(0)


def test_market_news_parses_xuangubao_items(client, monkeypatch) -> None:
    import app.news.service as news_service

    FakeClient.calls = []
    FakeClient.responses = [
        FakeResponse(
            {
                "data": {
                    "messages": [
                        {"id": 101, "title": "机器人板块异动拉升", "created_at": 1777334400, "url": "https://example.com/flash/101"}
                    ]
                }
            }
        )
    ]
    monkeypatch.setattr(news_service.httpx, "Client", FakeClient)

    response = client.get("/api/v1/news/market?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["errors"] == []
    assert payload["items"][0]["source"] == "xuangubao"
    assert payload["items"][0]["title"] == "机器人板块异动拉升"
    assert payload["items"][0]["published_at"]


def test_search_news_validates_empty_keyword(client) -> None:
    response = client.get("/api/v1/news/search?keyword=%20%20&limit=10")

    assert response.status_code == 422


def test_search_news_parses_jiuyangongshe_items(client, monkeypatch) -> None:
    import app.news.service as news_service

    FakeClient.calls = []
    FakeClient.responses = [
        FakeResponse(
            {
                "data": {
                    "list": [
                        {
                            "article_id": "a1",
                            "title": "宁德时代储能订单更新",
                            "ctime": 1777334500,
                            "author": "九研作者",
                            "url": "https://example.com/a1",
                        }
                    ]
                }
            }
        )
    ]
    monkeypatch.setattr(news_service.httpx, "Client", FakeClient)
    monkeypatch.setattr(news_service.NewsProvider, "_fetch_jiu_yan_token", lambda self: "token")

    response = client.get("/api/v1/news/search?keyword=宁德时代&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["errors"] == []
    assert payload["items"][0]["source"] == "jiuyangongshe"
    assert payload["items"][0]["author"] == "九研作者"
    assert payload["items"][0]["symbol_keyword"] == "宁德时代"
    assert FakeClient.calls[0][2]["keyword"] == "宁德时代"


def test_search_news_external_failure_returns_errors(client, monkeypatch) -> None:
    import app.news.service as news_service

    def fail(self, keyword: str, limit: int = 8):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(news_service.NewsProvider, "fetch_discussion_items", fail)

    response = client.get("/api/v1/news/search?keyword=宁德时代&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["errors"] == ["九研文章获取失败"]


def test_xueqiu_without_user_ids_returns_empty_with_hint(client, monkeypatch) -> None:
    import app.core.config as config_module
    import app.news.service as news_service

    monkeypatch.setenv("XUEQIU_USER_IDS", "")
    importlib.reload(config_module)
    monkeypatch.setattr(news_service, "settings", config_module.settings)

    response = client.get("/api/v1/news/xueqiu?limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["errors"] == ["雪球未配置"]


def test_xueqiu_with_user_ids_fetches_timeline(client, monkeypatch) -> None:
    import app.core.config as config_module
    import app.news.service as news_service

    monkeypatch.setenv("XUEQIU_USER_IDS", "5124430882")
    importlib.reload(config_module)
    monkeypatch.setattr(news_service, "settings", config_module.settings)
    FakeClient.calls = []
    FakeClient.responses = [
        FakeResponse(
            {
                "statuses": [
                    {
                        "id": 7,
                        "text": "关注用户观点更新",
                        "created_at": 1777334600000,
                        "target": "/123/456",
                        "user": {"screen_name": "雪球用户"},
                    }
                ]
            }
        )
    ]
    monkeypatch.setattr(news_service.httpx, "Client", FakeClient)

    response = client.get("/api/v1/news/xueqiu?limit=20")

    assert response.status_code == 200
    payload = response.json()
    assert payload["errors"] == []
    assert payload["items"][0]["source"] == "xueqiu"
    assert payload["items"][0]["author"] == "雪球用户"
    assert payload["items"][0]["url"] == "https://xueqiu.com/123/456"
    assert FakeClient.calls[0][1]["user_id"] == "5124430882"


def test_brief_returns_partial_data_when_source_fails(client, monkeypatch) -> None:
    import app.news.service as news_service
    from app.schemas.news import NewsItemRead

    monkeypatch.setattr(
        news_service.NewsProvider,
        "fetch_market_news_items",
        lambda self, limit=10: [NewsItemRead(id="m1", source="xuangubao", title="市场快讯")],
    )

    def fail_discussions(self, keyword: str, limit: int = 8):
        raise RuntimeError("discussion down")

    monkeypatch.setattr(news_service.NewsProvider, "fetch_discussion_items", fail_discussions)
    monkeypatch.setattr(news_service.NewsProvider, "get_xueqiu_feed", lambda self, limit=10: news_service.NewsFeedResponse(items=[], errors=["雪球未配置"]))

    response = client.get("/api/v1/news/brief?keyword=宁德时代&limit=10")

    assert response.status_code == 200
    payload = response.json()
    assert payload["market"][0]["title"] == "市场快讯"
    assert payload["discussions"] == []
    assert payload["xueqiu"] == []
    assert "九研文章获取失败" in payload["errors"]
    assert "雪球未配置" in payload["errors"]

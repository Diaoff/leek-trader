from datetime import date
from types import SimpleNamespace

from app.api import ai as ai_api_module
from app.ai.core_analyzer import build_stock_analysis_prompt
from app.ai.data_loader import AiDataLoader, AiStockContext
from app.market.data_service import DailyBarsPayload
from app.market.providers.base import DailyBarSnapshot
from app.market.symbols import normalize_a_share_symbol


def test_ai_config_can_be_loaded_and_updated(client):
    response = client.get("/api/v1/ai/config")
    assert response.status_code == 200
    assert response.json() == {
        "base_url": "",
        "api_key": "",
        "model": "",
        "configured": False,
    }

    update_response = client.put(
        "/api/v1/ai/config",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "secret-key",
            "model": "demo-model",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json() == {
        "base_url": "https://example.com/v1",
        "api_key": "secret-key",
        "model": "demo-model",
        "configured": True,
    }


def test_ai_chat_requires_complete_config(client):
    response = client.post(
        "/api/v1/ai/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "请分析一下今天市场风格",
                }
            ]
        },
    )
    assert response.status_code == 400
    assert "AI 配置不完整" in response.json()["detail"]


def test_ai_chat_returns_model_reply(client, monkeypatch):
    client.put(
        "/api/v1/ai/config",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "secret-key",
            "model": "demo-model",
        },
    )

    captured: dict[str, object] = {}

    def fake_request_completion(config, messages):
        captured["model"] = config.model
        captured["messages"] = messages
        return "这是模型回复"

    monkeypatch.setattr(ai_api_module.service, "_request_completion", fake_request_completion)

    response = client.post(
        "/api/v1/ai/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "请给我三条风险提示",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "content": "这是模型回复",
        "model": "demo-model",
    }
    assert captured["model"] == "demo-model"
    assert captured["messages"][0]["role"] == "system"


def test_ai_stock_analysis_uses_security_context(client, monkeypatch):
    client.put(
        "/api/v1/ai/config",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "secret-key",
            "model": "demo-model",
        },
    )

    monkeypatch.setattr(
        ai_api_module.service.data_loader,
        "load_stock_context",
        lambda symbol: AiStockContext(
            quote=SimpleNamespace(
                symbol=symbol,
                price=1415.74,
                change_percent=1.23,
                volume=3039624544.0,
                market_cap=1778000000000.0,
                ytd_change_percent=8.88,
            ),
            history_csv="日期,开盘,收盘\n2026-04-20,10,11",
        ),
    )

    captured: dict[str, object] = {}

    def fake_request_completion(config, messages):
        captured["messages"] = messages
        return "这是股票分析结果"

    monkeypatch.setattr(ai_api_module.service, "_request_completion", fake_request_completion)

    response = client.post(
        "/api/v1/ai/analyze-stock",
        json={
            "symbol": "sh600519",
            "note": "重点关注白酒消费复苏",
        },
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["symbol"] == "sh600519"
    assert payload["security"]["code"] == "600519"
    assert payload["security"]["name"]
    assert payload["content"] == "这是股票分析结果"
    assert payload["latest_price"] == 1415.74
    assert payload["change_percent"] == 1.23
    assert "重点关注白酒消费复苏" in captured["messages"][1]["content"]
    assert "日期,开盘,收盘" in captured["messages"][1]["content"]


def test_stock_analysis_prompt_includes_report_sections_and_context_gaps():
    prompt = build_stock_analysis_prompt(
        {
            "symbol": "sh600519",
            "code": "600519",
            "name": "贵州茅台",
            "market": "沪A",
            "tags": ["白酒"],
        },
        AiStockContext(quote=None, history_csv=""),
        "关注风险",
    )

    assert "AI 股票研究报告" in prompt
    assert "市场情绪与讨论线索" in prompt
    assert "暂无可用历史日线数据" in prompt
    assert "来源：none" in prompt
    assert "暂无可用数据" in prompt
    assert "仅供研究交流，不构成投资建议" in prompt


def test_history_loader_uses_canonical_market_data_csv():
    class StubMarketDataService:
        def get_quotes(self, symbols):
            return []

        def get_daily_bars_csv_with_source(self, symbol, limit=60):
            return "日期,开盘,收盘\n2026-01-23,83.23,81.2", "新浪日线"

    loader = AiDataLoader(market_data_service=StubMarketDataService())

    context = loader.load_stock_context("sz301667")

    assert context.history_source == "新浪日线"
    assert "2026-01-23" in context.history_csv


def test_ai_csv_is_generated_from_canonical_daily_bars():
    class StubMarketDataService:
        def get_quotes(self, symbols):
            return []

        def get_daily_bars_csv_with_source(self, symbol, limit=60):
            payload = DailyBarsPayload(
                source="eastmoney",
                bars=[
                    DailyBarSnapshot(
                        symbol="sz301667",
                        trade_date=date(2026, 1, 23),
                        open_price=83.23,
                        close_price=81.2,
                        high_price=83.8,
                        low_price=80.11,
                        volume=6363302.0,
                    )
                ],
            )
            from app.market.data_service import MarketDataService

            return MarketDataService._daily_bars_to_csv(payload.bars), "东方财富前复权日线"

    csv, source = AiDataLoader(market_data_service=StubMarketDataService()).fetch_recent_history_csv("301667.SZ")

    assert source == "东方财富前复权日线"
    assert csv.splitlines()[0] == "日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率"
    assert "2026-01-23,83.23,81.2,83.8,80.11,6363302.0" in csv


def test_ai_symbol_normalization_supports_exchange_suffixes(client, monkeypatch):
    client.put(
        "/api/v1/ai/config",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "secret-key",
            "model": "demo-model",
        },
    )

    captured: dict[str, object] = {}

    def fake_load_stock_context(symbol):
        captured["symbol"] = symbol
        return AiStockContext(
            quote=SimpleNamespace(
                symbol=symbol,
                price=119.82,
                change_percent=-5.13,
                volume=38270000.0,
                market_cap=5000000000.0,
                ytd_change_percent=None,
            ),
            history_csv="日期,开盘,收盘,最高,最低,成交量,成交额,振幅,涨跌幅,涨跌额,换手率\n2026-04-27,120,119.82,122,118,1000,38270000,3,-5.13,-6.48,2.1",
        )

    monkeypatch.setattr(ai_api_module.service.data_loader, "load_stock_context", fake_load_stock_context)
    monkeypatch.setattr(ai_api_module.service, "_request_completion", lambda config, messages: "这是股票分析结果")

    response = client.post(
        "/api/v1/ai/analyze-stock",
        json={"symbol": "301667.SZ"},
    )

    assert response.status_code == 200
    assert response.json()["symbol"] == "sz301667"
    assert captured["symbol"] == "sz301667"


def test_normalize_a_share_symbol_infers_common_markets():
    assert normalize_a_share_symbol("301667.SZ") == "sz301667"
    assert normalize_a_share_symbol("600519.SH") == "sh600519"
    assert normalize_a_share_symbol("301667") == "sz301667"


def test_ai_chat_stream_returns_sse_chunks(client, monkeypatch):
    client.put(
        "/api/v1/ai/config",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "secret-key",
            "model": "demo-model",
        },
    )

    monkeypatch.setattr(
        ai_api_module.service,
        "stream_chat",
        lambda db, tenant_id, messages: (iter(["第一段", "第二段"]), "demo-model"),
    )

    with client.stream(
        "POST",
        "/api/v1/ai/chat/stream",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "请流式输出",
                }
            ]
        },
    ) as response:
        payload = "".join(response.iter_text())

    assert response.status_code == 200
    assert 'event: meta' in payload
    assert 'event: chunk' in payload
    assert '第一段' in payload
    assert '第二段' in payload
    assert 'event: done' in payload


def test_ai_stock_analysis_stream_returns_meta_and_chunks(client, monkeypatch):
    client.put(
        "/api/v1/ai/config",
        json={
            "base_url": "https://example.com/v1",
            "api_key": "secret-key",
            "model": "demo-model",
        },
    )

    response_stub = {
        "symbol": "sh600519",
        "security": {
            "symbol": "sh600519",
            "code": "600519",
            "name": "贵州茅台",
            "market": "沪A",
            "tags": [],
        },
        "content": "",
        "generated_at": "2026-04-23T10:00:00+00:00",
        "latest_price": 1415.74,
        "change_percent": 1.23,
    }

    monkeypatch.setattr(
        ai_api_module.service,
        "stream_analyze_stock",
        lambda db, tenant_id, symbol, note: (
            SimpleNamespace(
                symbol=response_stub["symbol"],
                security=SimpleNamespace(model_dump=lambda: response_stub["security"]),
                generated_at=SimpleNamespace(isoformat=lambda: response_stub["generated_at"]),
                latest_price=response_stub["latest_price"],
                change_percent=response_stub["change_percent"],
            ),
            iter(["核心结论", "\n风险提示"]),
            "demo-model",
        ),
    )

    with client.stream(
        "POST",
        "/api/v1/ai/analyze-stock/stream",
        json={
            "symbol": "sh600519",
            "note": "测试",
        },
    ) as response:
        payload = "".join(response.iter_text())

    assert response.status_code == 200
    assert 'event: meta' in payload
    assert '贵州茅台' in payload
    assert '核心结论' in payload
    assert '风险提示' in payload

from types import SimpleNamespace

from app.api import ai as ai_api_module


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

    monkeypatch.setattr(ai_api_module.service, "_fetch_recent_history_csv", lambda symbol, limit=60: "日期,开盘,收盘\n2026-04-20,10,11")
    monkeypatch.setattr(
        ai_api_module.service,
        "quote_service",
        SimpleNamespace(
            list_quotes=lambda symbols: [
                SimpleNamespace(
                    symbol=symbols[0],
                    price=1415.74,
                    change_percent=1.23,
                    volume=3039624544.0,
                    market_cap=1778000000000.0,
                    ytd_change_percent=8.88,
                )
            ]
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
